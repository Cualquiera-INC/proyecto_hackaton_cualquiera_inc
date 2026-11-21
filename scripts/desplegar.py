"""Despliegue sin caída (actualización escalonada) y rollback de Nodo Ruta.

Uso:
  python scripts/desplegar.py desplegar [--version V]   construye y despliega una versión nueva
  python scripts/desplegar.py rollback [--version V]    vuelve a la versión anterior (o a V)
  python scripts/desplegar.py estado                    muestra versiones desplegadas y disponibles

Cómo evita la caída:
  1. Construye la imagen nueva (nodo-ruta:<version>) ANTES de tocar el servicio.
  2. Comprueba que app1, app2 y el proxy están sanos.
  3. Actualiza UNA instancia: mientras se recrea, NGINX envía todo a la otra.
  4. Espera a que la nueva esté healthy, que responda con la versión nueva y
     que el proxy ya la esté usando. Solo entonces actualiza la segunda.
  5. Si algún paso falla, devuelve las instancias tocadas a la versión anterior
     (rollback automático) y termina con código 1. La otra instancia nunca dejó
     de atender con la versión anterior.

Los códigos de salida (0 = éxito, 1 = fallo/rollback, 2 = uso incorrecto) permiten
llamarlo desde un pipeline (por ejemplo GitHub Actions) sin cambios.
"""
from pathlib import Path
import argparse, datetime, json, os, socket, subprocess, sys, time, urllib.request, urllib.error

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "despliegue"
COMPOSE = DIR / "compose.yaml"
ENV_FILE = DIR / ".env"
ESTADO = DIR / "estado.json"
DATOS = ROOT / "data" / "pedidos.json"
IMAGEN = "nodo-ruta"
SERVICIOS = ["app1", "app2"]


def puerto_configurado():
    """NODO_PUERTO del entorno; si no, el del despliegue en curso (.env); si no, 8080."""
    if os.environ.get("NODO_PUERTO"):
        return os.environ["NODO_PUERTO"]
    if ENV_FILE.exists():
        for linea in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if linea.startswith("NODO_PUERTO="):
                return linea.split("=", 1)[1].strip()
    return "8080"


PUERTO = puerto_configurado()

TIEMPO_SALUD = 60      # segundos máximos para que una instancia nueva quede healthy
TIEMPO_PROXY = 20      # segundos máximos para que el proxy la empiece a usar
TIEMPO_PRECONDICION = 30  # segundos máximos esperando a que todo esté sano antes de actualizar


class FalloDespliegue(Exception):
    pass


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def docker(*args, capturar=False, check=True, env=None):
    r = subprocess.run(["docker", *args], capture_output=capturar, text=True,
                       encoding="utf-8", errors="replace", env=env)
    if check and r.returncode != 0:
        detalle = (r.stderr or r.stdout or "").strip() if capturar else ""
        raise FalloDespliegue(f"docker {' '.join(args[:3])}... falló ({r.returncode}) {detalle}")
    return r.stdout.strip() if capturar else r.returncode


# ---------- estado y configuración ----------

def leer_estado():
    if ESTADO.exists():
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    return {"tags": {}, "actual": None, "anterior": None, "historial": []}


def guardar_estado(estado):
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def escribir_env(tags):
    """Fija la versión de cada instancia para Compose (también para comandos manuales)."""
    ENV_FILE.write_text(
        "# Generado por scripts/desplegar.py; no editar a mano.\n"
        f"APP1_TAG={tags['app1']}\nAPP2_TAG={tags['app2']}\nNODO_PUERTO={PUERTO}\n",
        encoding="utf-8")


def compose(*args, tags, capturar=False, check=True):
    env = dict(os.environ, APP1_TAG=tags["app1"], APP2_TAG=tags["app2"], NODO_PUERTO=PUERTO)
    return docker("compose", "-f", str(COMPOSE), *args, capturar=capturar, check=check, env=env)


def existe_imagen(tag):
    return subprocess.run(["docker", "image", "inspect", f"{IMAGEN}:{tag}"],
                          capture_output=True).returncode == 0


# ---------- comprobaciones ----------

def contenedor(svc, tags):
    return compose("ps", "-q", svc, tags=tags, capturar=True, check=False)


def estado_contenedor(cid):
    fmt = "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}|{{.RestartCount}}"
    out = docker("inspect", "--format", fmt, cid, capturar=True, check=False)
    partes = (out.split("|") + ["", "", "0"])[:3]
    return partes[0], partes[1], int(partes[2] or 0)


def esperar_sano(svc, tags, limite=TIEMPO_SALUD):
    inicio = time.monotonic()
    while time.monotonic() - inicio < limite:
        cid = contenedor(svc, tags)
        if cid:
            status, salud, reinicios = estado_contenedor(cid)
            if status in ("exited", "dead") or reinicios > 0:
                logs = docker("logs", "--tail", "15", cid, capturar=True, check=False)
                raise FalloDespliegue(f"{svc} falló al arrancar: el proceso terminó y Docker lo reinició "
                                      f"{reinicios} vez/veces (estado={status}). Últimos registros:\n{logs}")
            if salud == "unhealthy":
                raise FalloDespliegue(f"{svc} quedó unhealthy: /health no responde 200")
            if salud == "healthy":
                log(f"  {svc} healthy en {time.monotonic() - inicio:.1f} s")
                return
        time.sleep(1)
    raise FalloDespliegue(f"{svc} no quedó healthy en {limite} s")


def health_interno(svc, tags):
    codigo = ("import urllib.request;"
              "print(urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=2).read().decode())")
    out = compose("exec", "-T", svc, "python", "-c", codigo, tags=tags, capturar=True)
    return json.loads(out)


def consultar_proxy(ruta="/health"):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}{ruta}", timeout=2) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (OSError, ValueError):
        return None, {}


def confirmar_en_proxy(svc, tag, limite=TIEMPO_PROXY):
    """Espera hasta que el proxy entregue una respuesta de svc con la versión nueva."""
    inicio = time.monotonic()
    while time.monotonic() - inicio < limite:
        status, data = consultar_proxy()
        if status == 200 and data.get("instancia") == svc and data.get("version_app") == tag:
            log(f"  el proxy ya enruta a {svc} con {tag} ({time.monotonic() - inicio:.1f} s)")
            return
        time.sleep(0.3)
    raise FalloDespliegue(f"el proxy no enrutó a {svc} con la versión {tag} en {limite} s")


def todo_sano(tags):
    for svc in SERVICIOS + ["proxy"]:
        cid = contenedor(svc, tags)
        if not cid:
            return False, f"{svc} no existe"
        status, salud, _ = estado_contenedor(cid)
        if status != "running" or salud not in ("healthy", ""):
            return False, f"{svc} está {status}/{salud or 'sin healthcheck'}"
        if svc != "proxy" and salud != "healthy":
            return False, f"{svc} está {salud}"
    return True, ""


# ---------- operaciones ----------

def puerto_ocupado():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", int(PUERTO))) == 0


def construir(tag, estado):
    # Una versión que está o estuvo desplegada no se sobrescribe: es el punto de rollback.
    usadas = {estado.get("actual"), estado.get("anterior"), *estado.get("tags", {}).values()} | \
             {h["version"] for h in estado.get("historial", []) if h["resultado"] == "exitoso"}
    if tag in usadas:
        raise FalloDespliegue(f"La versión {tag} ya fue desplegada; use otra --version "
                              f"(o 'rollback --version {tag}' para volver a ella)")
    if existe_imagen(tag):
        log(f"La imagen {IMAGEN}:{tag} existe pero nunca se desplegó con éxito: se reconstruye")
    log(f"Construyendo {IMAGEN}:{tag} (el servicio actual sigue atendiendo)")
    docker("build", "-t", f"{IMAGEN}:{tag}", "--build-arg", f"APP_VERSION={tag}",
           "--label", f"nodo-ruta.version={tag}", str(ROOT))


def actualizar_instancia(svc, tag, tags):
    log(f"Actualizando {svc}: {tags[svc]} -> {tag}")
    tags[svc] = tag
    escribir_env(tags)
    compose("up", "-d", "--no-deps", svc, tags=tags)
    esperar_sano(svc, tags)
    info = health_interno(svc, tags)
    if info.get("version_app") != tag or info.get("estado") != "ok":
        raise FalloDespliegue(f"{svc} responde {info}, se esperaba version_app={tag}")
    log(f"  {svc} responde version_app={tag}, datos={info.get('version_datos')}")
    confirmar_en_proxy(svc, tag)


def escalonado(tag, estado, accion):
    """Actualiza app1 y luego app2; ante cualquier fallo revierte lo tocado."""
    previos = dict(estado["tags"])
    tags = dict(previos)
    # Si algún contenedor acaba de arrancar (healthcheck en "starting"), se espera
    # un poco en vez de abortar; si sigue mal tras el límite, no se toca nada.
    limite = time.monotonic() + TIEMPO_PRECONDICION
    ok, motivo = todo_sano(tags)
    while not ok and time.monotonic() < limite:
        time.sleep(1)
        ok, motivo = todo_sano(tags)
    if not ok:
        raise FalloDespliegue(f"Precondición no cumplida tras {TIEMPO_PRECONDICION} s: {motivo}. "
                              "No se actualiza para no dejar el servicio sin instancias.")
    log(f"Precondición: app1, app2 y proxy sanos. Versión actual: {previos}")
    tocadas = []
    inicio = time.monotonic()
    try:
        for svc in SERVICIOS:
            tocadas.append(svc)
            actualizar_instancia(svc, tag, tags)
    except FalloDespliegue as e:
        log(f"ERROR: {e}")
        log("ROLLBACK automático: devolviendo las instancias tocadas a su versión anterior")
        for svc in tocadas:
            tags[svc] = previos[svc]
            escribir_env(tags)
            compose("up", "-d", "--no-deps", svc, tags=tags)
            esperar_sano(svc, tags)
            log(f"  {svc} restaurada a {previos[svc]}")
        registrar(estado, accion, tag, "fallido_revertido", time.monotonic() - inicio, str(e).splitlines()[0])
        log(f"Despliegue de {tag} REVERTIDO. El servicio sigue en {previos}.")
        return False
    estado["anterior"], estado["actual"], estado["tags"] = estado["actual"], tag, tags
    registrar(estado, accion, tag, "exitoso", time.monotonic() - inicio)
    log(f"Despliegue de {tag} completado en {time.monotonic() - inicio:.1f} s. Anterior disponible para rollback: {estado['anterior']}")
    return True


def primer_despliegue(tag, estado):
    log("No hay despliegue previo: se levantan app1, app2 y proxy")
    tags = {"app1": tag, "app2": tag}
    escribir_env(tags)
    inicio = time.monotonic()
    compose("up", "-d", tags=tags)
    for svc in SERVICIOS:
        esperar_sano(svc, tags)
        confirmar_en_proxy(svc, tag)
    esperar_sano("proxy", tags)
    estado.update(actual=tag, anterior=estado.get("actual"), tags=tags)
    registrar(estado, "desplegar", tag, "exitoso", time.monotonic() - inicio, "despliegue inicial")
    log(f"Despliegue inicial de {tag} listo en http://127.0.0.1:{PUERTO}")
    return True


def registrar(estado, accion, tag, resultado, segundos, detalle=""):
    estado["historial"].append({
        "fecha": datetime.datetime.now().isoformat(timespec="seconds"),
        "accion": accion, "version": tag, "resultado": resultado,
        "segundos": round(segundos, 1), "detalle": detalle})
    guardar_estado(estado)


def version_por_defecto():
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip() or "sin-git"
    return f"{datetime.datetime.now():%Y%m%d-%H%M%S}-{sha}"


def main():
    p = argparse.ArgumentParser(description="Despliegue sin caída y rollback de Nodo Ruta")
    p.add_argument("accion", choices=["desplegar", "rollback", "estado"])
    p.add_argument("--version", help="desplegar: nombre de la versión nueva; rollback: versión a la que volver")
    a = p.parse_args()

    if not DATOS.is_file():
        p.exit(2, "Falta data/pedidos.json. Ejecute: python scripts/datos.py preparar\n")
    estado = leer_estado()

    if a.accion == "estado":
        print(json.dumps({k: estado[k] for k in ("actual", "anterior", "tags")}, ensure_ascii=False, indent=2))
        print("Últimas operaciones:")
        for h in estado["historial"][-5:]:
            print(f"  {h['fecha']} {h['accion']:<9} {h['version']:<28} {h['resultado']} ({h['segundos']} s) {h['detalle']}")
        print("Versiones disponibles para rollback:")
        print(docker("image", "ls", IMAGEN, "--format", "  {{.Tag}}\t{{.CreatedSince}}", capturar=True))
        return 0

    try:
        if a.accion == "desplegar":
            tag = a.version or version_por_defecto()
            inicial = not estado["actual"] or not contenedor("app1", estado["tags"])
            proxy_propio = contenedor("proxy", estado["tags"] or {"app1": tag, "app2": tag})
            if inicial and puerto_ocupado() and not (proxy_propio and estado_contenedor(proxy_propio)[0] == "running"):
                p.exit(1, f"El puerto {PUERTO} ya está en uso por otro programa. Si es el laboratorio de la ayuda "
                          f"opcional, deténgalo con:\n  docker compose -f ayuda_opcional/compose.yaml down\n"
                          f"o use otro puerto: $env:NODO_PUERTO='8081'\n")
            construir(tag, estado)
            if inicial:
                return 0 if primer_despliegue(tag, estado) else 1
            return 0 if escalonado(tag, estado, "desplegar") else 1

        # rollback
        if not estado["actual"]:
            p.exit(2, "No hay ningún despliegue registrado.\n")
        tag = a.version or estado["anterior"]
        if not tag:
            p.exit(2, "No hay versión anterior registrada; indique --version.\n")
        if not existe_imagen(tag):
            p.exit(2, f"La imagen {IMAGEN}:{tag} no existe localmente.\n")
        if tag == estado["actual"]:
            p.exit(2, f"{tag} ya es la versión desplegada.\n")
        log(f"Rollback a {tag} (escalonado, sin caída)")
        return 0 if escalonado(tag, estado, "rollback") else 1
    except FalloDespliegue as e:
        log(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
