"""Despliegue de Nodo Ruta en AWS (us-east-2) con un solo comando.

Automatiza lo que antes eran ~10 bloques pegados a mano (infra/aws/README.md y PRUEBAS.md):
secretos en SSM, las 4 pilas de CloudFormation en orden, la publicación del front, la espera
a que el balanceador vea sanas las 2 instancias, la prueba de humo y la destrucción total.

Uso:
  python scripts/aws_nodo.py estado
  python scripts/aws_nodo.py desplegar [--cidr 203.0.113.7/32] [--version COMMIT] [--permitir-reemplazo] [--evidencia AWS09]
  python scripts/aws_nodo.py probar [--evidencia AWS09]
  python scripts/aws_nodo.py destruir [--si] [--conservar-secretos] [--evidencia AWS09]
  python scripts/aws_nodo.py --simular desplegar      (solo lecturas; muestra lo que ejecutaría)

En GitHub Actions (.github/workflows/aws.yml) se usa con --cidr, --si y --evidencia; ahí la prueba de
humo se hace por SSM en las EC2 (el runner no es la IP de CidrAcceso), también con --humo-remoto.

Requisitos: AWS CLI v2 con credenciales activas, git, y npm (para construir el front).
Solo biblioteca estándar; llama al AWS CLI con subprocess (sin bash), así que corre igual en
macOS, Windows y Linux.

Cómo se comporta:
  - Idempotente: una pila que no existe se crea; una que existe se actualiza con un conjunto de
    cambios (change set) y se ABORTA si algún recurso se reemplazaría (Replacement True o
    Conditional), salvo --permitir-reemplazo. "Sin cambios" cuenta como éxito. Una pila que quedó
    en ROLLBACK_COMPLETE (creación fallida) se borra y se vuelve a crear.
  - Secretos: se crean en SSM Parameter Store (SecureString) solo si faltan, con la biblioteca
    secrets. Nunca se imprimen ni se escriben en el repo. Se pasan a AWS por archivos temporales
    con permisos 0600 en el directorio temporal del sistema, que se borran al terminar (no quedan
    en la línea de comandos ni en el historial).
  - Fallos: se imprimen los eventos FAILED de la pila (recurso y motivo) y el código de salida es 1.
  - --simular: solo lecturas; lo que crearía, actualizaría o borraría se muestra con [simular].

Códigos de salida: 0 éxito, 1 fallo (o prueba no superada), 2 uso incorrecto.
Solo datos sintéticos. Región fija us-east-2 (la política de la organización bloquea las demás).
"""
import argparse
import contextlib
import datetime
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
INFRA = RAIZ / "infra" / "aws"
REGION = "us-east-2"
REGION_GLOBAL = "us-east-1"          # el API de etiquetas muestra CloudFront desde us-east-1
ETIQUETA = "proyecto=nodo-ruta"
URL_REPO = "Cualquiera-INC/proyecto_hackaton_cualquiera_inc"

PILA_RED, PILA_DATOS, PILA_COMPUTO, PILA_FRONT = ("nodo-ruta-red", "nodo-ruta-datos",
                                                  "nodo-ruta-computo", "nodo-ruta-front")
# (pila, plantilla, parámetros que en una actualización conservan su valor anterior)
PILAS = [
    (PILA_RED, "01-red.yaml", ["CidrVpc"]),
    (PILA_DATOS, "02-datos.yaml", ["PilaRed", "ClaseInstancia", "NombreBase", "UsuarioBase",
                                   "RutaParametroClave", "CrearBucket"]),
    (PILA_COMPUTO, "03-computo.yaml", ["PilaRed", "PilaDatos", "UrlRepo", "TipoInstancia",
                                       "AmiX86", "AmiArm"]),
    (PILA_FRONT, "04-front.yaml", ["PilaComputo"]),
]
SSM_CLAVE_DB = "/nodo-ruta/db/password"
SSM_CLAVE_ORIGEN = "/nodo-ruta/front/clave-origen"
# Rutas del repo que las EC2 o el front toman del commit: si tienen cambios sin confirmar, el
# despliegue no sería lo que está en GitHub.
RUTAS_RELEVANTES = ("infra/aws/", "despliegue/", "servicios/", "basedatos/", "frontend-nodo/", "data/",
                    "app.py", "Dockerfile", "pedidos.json")
# Recursos con la etiqueta que existen a propósito y no son parte del despliegue.
PERMANENTES = ("github-actions-nodo-ruta", "oidc-provider/token.actions.githubusercontent.com", ":budget/")

TIEMPO_PILA = 3600        # segundos máximos esperando una pila (RDS y CloudFront tardan)
TIEMPO_DESTINOS = 900     # ~15 min para que los 2 destinos del target group estén healthy

SIMULAR = False
AWS = None
BITACORA = []
PASOS = []                # (nombre, segundos, resultado)

ENTORNO = dict(os.environ, AWS_DEFAULT_REGION=REGION, AWS_REGION=REGION, AWS_PAGER="",
               AWS_CLI_AUTO_PROMPT="off", PYTHONIOENCODING="utf-8")


class Fallo(Exception):
    pass


class ErrorAws(Exception):
    def __init__(self, cmd, codigo, stderr):
        super().__init__(f"{' '.join(cmd[:4])} -> codigo {codigo}: {stderr.strip()}")
        self.codigo, self.stderr = codigo, stderr


# ---------------------------------------------------------------- utilidades

def log(msg=""):
    linea = f"[{datetime.datetime.now():%H:%M:%S}] {msg}" if msg else ""
    print(linea, flush=True)
    BITACORA.append(linea)


def dur(seg):
    seg = int(round(seg))
    return f"{seg // 60} min {seg % 60:02d} s" if seg >= 60 else f"{seg} s"


def ahora_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def fecha_api(texto):
    return datetime.datetime.fromisoformat(texto.replace("Z", "+00:00"))


def mostrar(cmd):
    return " ".join(shlex.quote(c) for c in cmd)


@contextlib.contextmanager
def paso(nombre):
    """Cronometra un paso, lo muestra con marca de tiempo y lo guarda para el resumen."""
    log(f"== {nombre}")
    t0 = time.monotonic()
    resultado = "ok"
    try:
        yield
    except BaseException:
        resultado = "FALLO"
        raise
    finally:
        PASOS.append((nombre, time.monotonic() - t0, resultado))
        log(f"   {nombre}: {resultado} en {dur(time.monotonic() - t0)}")


@contextlib.contextmanager
def archivo_privado(contenido):
    """Archivo temporal con permisos 0600 en el directorio temporal del sistema; se borra al salir.

    En simulación no se crea nada (solo devuelve un marcador)."""
    if SIMULAR:
        yield "<archivo-temporal-0600>"
        return
    fd, ruta = tempfile.mkstemp(prefix="nodo-ruta-", suffix=".json")
    try:
        try:
            os.chmod(ruta, 0o600)          # mkstemp ya lo crea 0600; en Windows chmod casi no aplica
        except OSError:
            pass
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(contenido)
        yield ruta
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(ruta)


def aws(*args, lectura=True, region=REGION):
    """Ejecuta el AWS CLI. Devuelve el JSON ya leído (o None si no hay salida).

    Con lectura=False y --simular solo muestra el comando y devuelve None."""
    cmd = [AWS, *args, "--region", region, "--output", "json"]
    if not lectura and SIMULAR:
        log(f"   [simular] $ {mostrar(cmd)}")
        return None
    proc = subprocess.run(cmd, text=True, capture_output=True, env=ENTORNO)
    if proc.returncode != 0:
        raise ErrorAws(cmd, proc.returncode, proc.stderr)
    salida = proc.stdout.strip()
    if not salida or salida == "null":
        return None
    return json.loads(salida)


def aws_si_existe(*args, **kw):
    """Como aws(), pero devuelve None cuando el recurso no existe en vez de fallar."""
    try:
        return aws(*args, **kw)
    except ErrorAws as e:
        if any(t in e.stderr for t in ("does not exist", "NoSuchBucket", "ParameterNotFound")):
            return None
        raise


def git(*args, tolerar=False):
    proc = subprocess.run(["git", *args], cwd=RAIZ, text=True, capture_output=True)
    if proc.returncode != 0 and not tolerar:
        raise Fallo(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout.rstrip() if proc.returncode == 0 else None


# ---------------------------------------------------------------- CloudFormation

def describir_pila(ref):
    r = aws_si_existe("cloudformation", "describe-stacks", "--stack-name", ref)
    return r["Stacks"][0] if r else None


def salidas(pila):
    p = describir_pila(pila)
    return {o["OutputKey"]: o["OutputValue"] for o in (p or {}).get("Outputs", [])}


def eventos_fallidos(ref, desde):
    """Eventos FAILED de la pila posteriores a 'desde' (los más antiguos primero)."""
    try:
        r = aws("cloudformation", "describe-stack-events", "--stack-name", ref)
    except ErrorAws:
        return []
    ev = [e for e in r["StackEvents"] if "FAILED" in e["ResourceStatus"] and fecha_api(e["Timestamp"]) >= desde]
    return sorted(ev, key=lambda e: e["Timestamp"])


def informar_fallo(ref, nombre, desde):
    log(f"   Eventos FAILED de {nombre}:")
    ev = eventos_fallidos(ref, desde - datetime.timedelta(seconds=30))
    for e in ev:
        log(f"   - {e['LogicalResourceId']} ({e['ResourceStatus']}): {e.get('ResourceStatusReason', '(sin motivo)')}")
    if not ev:
        log("   (no hay eventos FAILED; revisa 'aws cloudformation describe-stack-events')")


def esperar_pila(ref, nombre, intervalo=10):
    """Espera a que la pila salga de *_IN_PROGRESS y devuelve su estado final."""
    t0 = ultimo_aviso = time.monotonic()
    ultimo = None
    while True:
        p = describir_pila(ref)
        if p is None:
            return "DELETE_COMPLETE"
        estado = p["StackStatus"]
        ahora = time.monotonic()
        if estado != ultimo or ahora - ultimo_aviso >= 60:
            log(f"   {nombre}: {estado} ({dur(ahora - t0)})")
            ultimo, ultimo_aviso = estado, ahora
        if not estado.endswith("_IN_PROGRESS"):
            return estado
        if ahora - t0 > TIEMPO_PILA:
            raise Fallo(f"{nombre} sigue en {estado} tras {dur(TIEMPO_PILA)}")
        time.sleep(intervalo)


def parametros_json(pares, previos, existe):
    """Lista de parámetros de CloudFormation. En una actualización, 'previos' conservan su valor."""
    lista = [{"ParameterKey": k, "ParameterValue": v} for k, v in pares]
    if existe:
        lista += [{"ParameterKey": k, "UsePreviousValue": True} for k in previos]
    return lista


def mostrar_parametros(lista):
    visibles = []
    for p in lista:
        if p["ParameterKey"] == "ClaveOrigen":
            visibles.append("ClaveOrigen=***")
        elif p.get("UsePreviousValue"):
            visibles.append(f"{p['ParameterKey']}=(valor anterior)")
        else:
            visibles.append(f"{p['ParameterKey']}={p['ParameterValue']}")
    return ", ".join(visibles) or "(ninguno)"


def capacidades(plantilla):
    return ["CAPABILITY_IAM"] if "AWS::IAM::" in plantilla.read_text(encoding="utf-8") else []


def asegurar_pila(nombre, plantilla, pares, previos, permitir_reemplazo):
    """Crea la pila si no existe; si existe la actualiza con un conjunto de cambios revisado."""
    ruta = INFRA / plantilla
    cap = capacidades(ruta)
    p = describir_pila(nombre)
    if p and p["StackStatus"] == "DELETE_IN_PROGRESS" and SIMULAR:
        log(f"   {nombre} se está borrando; en la ejecución real se espera y luego se crea")
        p = None
    elif p and p["StackStatus"].endswith("_IN_PROGRESS"):
        log(f"   {nombre} está en {p['StackStatus']}; espero a que termine")
        if not SIMULAR:
            esperar_pila(nombre, nombre)
            p = describir_pila(nombre)
    if p and p["StackStatus"] in ("ROLLBACK_COMPLETE", "CREATE_FAILED", "DELETE_FAILED", "ROLLBACK_FAILED",
                                  "REVIEW_IN_PROGRESS"):
        log(f"   {nombre} quedó en {p['StackStatus']} (creación fallida): se borra para volver a crearla")
        borrar_pila(nombre)
        p = None
    existe = p is not None
    lista = parametros_json(pares, previos, existe)
    log(f"   {nombre}: {'actualizar' if existe else 'crear'} con {plantilla}; parámetros: {mostrar_parametros(lista)}")
    clave_etiqueta, valor_etiqueta = ETIQUETA.split("=")
    comunes = ["--template-body", f"file://{ruta}", "--tags", f"Key={clave_etiqueta},Value={valor_etiqueta}"]
    if cap:
        comunes += ["--capabilities", *cap]
    t0 = ahora_utc()
    cs = f"aws-nodo-{int(time.time())}"
    with archivo_privado(json.dumps(lista)) as pf:
        param = ["--parameters", f"file://{pf}"] if lista else []
        if not existe:
            aws("cloudformation", "create-stack", "--stack-name", nombre, *comunes, *param, lectura=False)
        else:
            aws("cloudformation", "create-change-set", "--stack-name", nombre, "--change-set-name", cs,
                "--change-set-type", "UPDATE", *comunes, *param, lectura=False)
    if SIMULAR:
        if existe:
            log("   [simular] luego se revisaría el conjunto de cambios (abortar si Replacement es True o Conditional) y se ejecutaría")
        return
    if existe and not ejecutar_cambios(nombre, cs, permitir_reemplazo):
        return                                        # sin cambios: ya estaba al día
    estado = esperar_pila(nombre, nombre)
    esperado = "UPDATE_COMPLETE" if existe else "CREATE_COMPLETE"
    if estado != esperado:
        informar_fallo(nombre, nombre, t0)
        raise Fallo(f"{nombre} terminó en {estado} (se esperaba {esperado})")


def ejecutar_cambios(nombre, cs, permitir_reemplazo):
    """Revisa el conjunto de cambios y lo ejecuta. False si no había cambios."""
    t_limite = time.monotonic() + 300
    while True:
        r = aws("cloudformation", "describe-change-set", "--stack-name", nombre, "--change-set-name", cs)
        if r["Status"] in ("CREATE_COMPLETE", "FAILED"):
            break
        if time.monotonic() > t_limite:
            raise Fallo(f"el conjunto de cambios de {nombre} no terminó de crearse")
        time.sleep(3)
    motivo = r.get("StatusReason", "")
    if r["Status"] == "FAILED":
        aws("cloudformation", "delete-change-set", "--stack-name", nombre, "--change-set-name", cs, lectura=False)
        if "didn't contain changes" in motivo or "No updates are to be performed" in motivo:
            log(f"   {nombre}: sin cambios (No updates are to be performed): se considera éxito")
            return False
        raise Fallo(f"no se pudo crear el conjunto de cambios de {nombre}: {motivo}")
    peligro = []
    for c in r.get("Changes", []):
        rc = c["ResourceChange"]
        reemplazo = rc.get("Replacement", "-")
        log(f"   cambio: {rc['LogicalResourceId']:<28} {rc['Action']:<8} reemplazo={reemplazo}")
        if reemplazo in ("True", "Conditional"):
            peligro.append(rc["LogicalResourceId"])
    if peligro and not permitir_reemplazo:
        aws("cloudformation", "delete-change-set", "--stack-name", nombre, "--change-set-name", cs, lectura=False)
        raise Fallo(f"{nombre}: se reemplazarían {', '.join(peligro)} (Replacement True/Conditional). "
                    "No se aplicó nada. Si es intencional (nuevo --version o una AMI más nueva), "
                    "repite con --permitir-reemplazo.")
    if peligro:
        log(f"   AVISO: se reemplazan {', '.join(peligro)} (permitido con --permitir-reemplazo)")
    aws("cloudformation", "execute-change-set", "--stack-name", nombre, "--change-set-name", cs, lectura=False)
    # El conjunto pasa de AVAILABLE a EXECUTE_IN_PROGRESS y luego a EXECUTE_COMPLETE; así no se confunde
    # el estado anterior de la pila (UPDATE_COMPLETE) con el final de esta actualización.
    t_limite = time.monotonic() + TIEMPO_PILA
    while time.monotonic() < t_limite:
        r = aws("cloudformation", "describe-change-set", "--stack-name", nombre, "--change-set-name", cs)
        if r.get("ExecutionStatus") in ("EXECUTE_COMPLETE", "EXECUTE_FAILED", "OBSOLETE", "UNAVAILABLE"):
            break
        time.sleep(10)
    return True


def borrar_pila(nombre):
    """Borra la pila y espera. Tolera que ya no exista."""
    p = describir_pila(nombre)
    if p is None:
        log(f"   {nombre}: ya no existe")
        return
    ref = p["StackId"]
    log(f"   borrar {nombre} (estado {p['StackStatus']})")
    t0 = ahora_utc()
    aws("cloudformation", "delete-stack", "--stack-name", nombre, lectura=False)
    if SIMULAR:
        return
    estado = esperar_pila(ref, nombre)
    if estado != "DELETE_COMPLETE":
        informar_fallo(ref, nombre, t0)
        raise Fallo(f"{nombre} no se pudo borrar (estado {estado})")


# ---------------------------------------------------------------- SSM, git, red

def ssm_existe(nombre):
    r = aws("ssm", "describe-parameters", "--parameter-filters", f"Key=Name,Option=Equals,Values={nombre}")
    return bool(r and r.get("Parameters"))


def asegurar_secreto(nombre, nbytes):
    if ssm_existe(nombre):
        log(f"   {nombre}: ya existe (no se toca)")
        return
    log(f"   {nombre}: falta; se crea como SecureString (valor aleatorio, no se muestra)")
    entrada = {"Name": nombre, "Type": "SecureString", "Tier": "Standard", "Value": secrets.token_hex(nbytes),
               "Tags": [{"Key": "proyecto", "Value": "nodo-ruta"}]}
    with archivo_privado(json.dumps(entrada)) as ruta:
        aws("ssm", "put-parameter", "--cli-input-json", f"file://{ruta}", lectura=False)


def leer_secreto(nombre):
    """Lee un SecureString descifrado. Nunca se imprime."""
    if SIMULAR and not ssm_existe(nombre):
        return "<secreto-por-crear>"
    return aws("ssm", "get-parameter", "--name", nombre, "--with-decryption", "--query", "Parameter.Value")


def prefix_list_cloudfront():
    r = aws("ec2", "describe-managed-prefix-lists", "--filters",
            "Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing",
            "--query", "PrefixLists[0].PrefixListId")
    return r if isinstance(r, str) and r.startswith("pl-") else None


def ip_publica():
    try:
        with urllib.request.urlopen("https://checkip.amazonaws.com", timeout=10) as r:
            ip = r.read().decode().strip()
    except OSError as e:
        raise Fallo(f"no pude detectar tu IP pública ({e}); usa --cidr X.X.X.X/32")
    if not re.fullmatch(r"(\d{1,3}\.){3}\d{1,3}", ip):
        raise Fallo(f"checkip devolvió algo que no es una IPv4: {ip!r}; usa --cidr")
    return ip


def validar_cidr(cidr):
    if not re.fullmatch(r"(\d{1,3}\.){3}\d{1,3}/\d{1,2}", cidr) or cidr == "0.0.0.0/0":
        raise Fallo(f"CIDR inválido o abierto a todo: {cidr} (ejemplo: 203.0.113.7/32)")
    return cidr


def resolver_commit(version):
    """Hash completo del commit a desplegar y comprobación de que existe en GitHub."""
    origen = git("remote", "get-url", "origin")
    if URL_REPO.lower() not in origen.lower():
        raise Fallo(f"'origin' ({origen}) no es {URL_REPO}; las EC2 clonan ese repo y no verían tu commit")
    if version:
        commit = git("rev-parse", "--verify", f"{version}^{{commit}}", tolerar=True)
        if not commit:
            raise Fallo(f"--version {version}: no existe ese commit en tu repo local")
    else:
        linea = git("ls-remote", "origin", "refs/heads/main", tolerar=True)
        if not linea:
            raise Fallo("no pude leer origin/main con 'git ls-remote' (sin red o sin acceso)")
        commit = linea.split()[0]
    remotos = [l.split()[0] for l in git("ls-remote", "--heads", "--tags", "origin").splitlines()]
    publicado = commit in remotos
    if not publicado:
        # Un commit que no es la punta de una rama: debe ser ancestro de alguna punta remota.
        git("fetch", "--quiet", "origin")
        for punta in remotos:
            if subprocess.run(["git", "merge-base", "--is-ancestor", commit, punta], cwd=RAIZ,
                              capture_output=True).returncode == 0:
                publicado = True
                break
    if not publicado:
        raise Fallo(f"el commit {commit} no está en GitHub (git ls-remote); haz 'git push' primero: las EC2 lo clonan")
    return commit


def comprobar_git():
    sucios = []
    for linea in git("status", "--porcelain").splitlines():
        ruta = linea[3:].split(" -> ")[-1].strip('"')
        if ruta.startswith(RUTAS_RELEVANTES):
            sucios.append(linea)
    return sucios


# ---------------------------------------------------------------- comprobaciones de servicio

def esperar_destinos(arn):
    log(f"   esperando 2 destinos healthy (máximo {dur(TIEMPO_DESTINOS)})")
    t0 = time.monotonic()
    ultimo, ultimo_aviso = None, t0
    while True:
        r = aws("elbv2", "describe-target-health", "--target-group-arn", arn)
        estados = {t["Target"]["Id"]: t["TargetHealth"]["State"] for t in (r or {}).get("TargetHealthDescriptions", [])}
        ahora = time.monotonic()
        if estados != ultimo or ahora - ultimo_aviso >= 30:
            log(f"   destinos ({dur(ahora - t0)}): {estados or 'sin destinos registrados'}")
            ultimo, ultimo_aviso = dict(estados), ahora
        if len(estados) >= 2 and all(v == "healthy" for v in estados.values()):
            log(f"   los {len(estados)} destinos están healthy tras {dur(ahora - t0)}")
            return
        if ahora - t0 > TIEMPO_DESTINOS:
            raise Fallo(f"los destinos no llegaron a healthy en {dur(TIEMPO_DESTINOS)}: {estados}. "
                        "Revisa el arranque por SSM: sudo tail /var/log/nodo-ruta-arranque.log")
        time.sleep(15)


_getaddrinfo = socket.getaddrinfo


def _solo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return _getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


def http_get(url, timeout=15):
    """GET sin excepciones por 4xx/5xx. Devuelve (código, tipo, cuerpo)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


def con_reintentos(nombre, fn, intentos=8, pausa=10):
    """CloudFront y las EC2 pueden tardar unos segundos: reintenta antes de dar la prueba por fallida."""
    ultimo = ""
    for i in range(1, intentos + 1):
        try:
            return fn()
        except (Fallo, OSError, ValueError, KeyError) as e:
            ultimo = str(e)
            log(f"   {nombre}: intento {i}/{intentos} falló ({ultimo})")
            if i < intentos:
                time.sleep(pausa)
    raise Fallo(f"{nombre}: {ultimo}")


def prueba_humo(url):
    url = url.rstrip("/")
    log(f"   URL: {url}")
    socket.getaddrinfo = _solo_ipv4        # la función de CloudFront solo conoce tu IPv4

    def raiz():
        c, tipo, _ = http_get(url + "/")
        if c != 200 or "text/html" not in tipo.lower():
            raise Fallo(f"/ devolvió {c} {tipo}")
        return c, tipo

    def pedidos():
        c, _, cuerpo = http_get(url + "/pedidos")
        if c != 200:
            raise Fallo(f"/pedidos devolvió {c}")
        n = len(json.loads(cuerpo)["pedidos"])
        if n != 6:
            raise Fallo(f"/pedidos trajo {n} pedidos (se esperaban 6)")
        return n

    def salud():
        vistas = {}
        for _ in range(30):
            c, _, cuerpo = http_get(url + "/health")
            if c != 200:
                raise Fallo(f"/health devolvió {c}")
            d = json.loads(cuerpo)
            vistas[d["instancia"]] = d.get("estado")
            zonas = {m.group(1) for m in (re.match(r"(us-east-2[a-z])", i) for i in vistas) if m}
            if len(zonas) >= 2:
                return vistas, zonas
            time.sleep(0.3)
        raise Fallo(f"/health respondió solo desde {sorted(vistas)} tras 30 consultas")

    try:
        c, tipo = con_reintentos("GET /", raiz)
        log(f"   OK  /          {c} {tipo}")
        n = con_reintentos("GET /pedidos", pedidos)
        log(f"   OK  /pedidos   200 con {n} pedidos")
        vistas, zonas = con_reintentos("GET /health", salud)
        log(f"   OK  /health    alterna entre {sorted(zonas)}: {vistas}")
        if any(v != "ok" for v in vistas.values()):
            log("   AVISO: alguna instancia responde con estado distinto de 'ok'")
    finally:
        socket.getaddrinfo = _getaddrinfo


def en_actions():
    """True dentro de GitHub Actions: el runner no tiene la IP de CidrAcceso, así que CloudFront le da 403."""
    return os.environ.get("GITHUB_ACTIONS") == "true"


def prueba_humo_remota(url, ids):
    """Prueba de humo cuando quien la corre NO es la IP permitida (GitHub Actions o --humo-remoto).

    1) Desde aquí: CloudFront debe responder (200 si esta IP casualmente está permitida; 403 si no, que
       además comprueba que la restricción por IP funciona).
    2) Por SSM, en cada EC2: /health (estado ok) y /pedidos (6 pedidos) contra el puerto 8080 local."""
    url = url.rstrip("/")
    socket.getaddrinfo = _solo_ipv4
    try:
        def raiz():
            c, _, _ = http_get(url + "/")
            if c not in (200, 403):
                raise Fallo(f"CloudFront devolvió {c} (se esperaba 200 o 403)")
            return c
        c = con_reintentos("GET / (CloudFront)", raiz)
        log(f"   CloudFront responde {c} a esta IP ({'permitida' if c == 200 else 'no está en CidrAcceso: es lo esperado'})")
    finally:
        socket.getaddrinfo = _getaddrinfo
    cmd = ("curl -fsS http://127.0.0.1:8080/health; echo; "
           "curl -fsS http://127.0.0.1:8080/pedidos | python3 -c "
           "\"import json,sys; print('PEDIDOS', len(json.load(sys.stdin)['pedidos']))\"")
    for instancia in ids:
        estado, salida, error = ssm_ejecutar(instancia, cmd)
        log(f"   {instancia}: {estado} {salida.strip()} {error.strip()}".rstrip())
        if estado != "Success" or "PEDIDOS 6" not in salida or '"estado"' not in salida or "ok" not in salida.split("PEDIDOS")[0]:
            raise Fallo(f"la prueba local por SSM falló en {instancia}")


def comprobar_servicio(a):
    """Prueba de humo por CloudFront o, si no se puede (Actions), por SSM en cada EC2."""
    url = salidas(PILA_FRONT)["UrlFront"]
    if getattr(a, "humo_remoto", False) or en_actions():
        c = salidas(PILA_COMPUTO)
        prueba_humo_remota(url, [c["IdInstanciaA"], c["IdInstanciaB"]])
    else:
        prueba_humo(url)
    return url


def ssm_ejecutar(instancia, comando, timeout=420):
    """Ejecuta un comando como root en una EC2 por SSM y devuelve (estado, salida, error)."""
    log(f"   SSM en {instancia}: {comando}")
    cuerpo = json.dumps({"commands": [comando]})
    cid = None
    for i in range(1, 11):         # el agente de SSM puede tardar en registrarse tras el arranque
        try:
            with archivo_privado(cuerpo) as ruta:
                cid = aws("ssm", "send-command", "--instance-ids", instancia, "--document-name", "AWS-RunShellScript",
                          "--parameters", f"file://{ruta}", "--query", "Command.CommandId")
            break
        except ErrorAws as e:
            if "InvalidInstanceId" not in e.stderr or i == 10:
                raise
            log(f"   SSM aún no ve la instancia (intento {i}/10)")
            time.sleep(15)
    t0 = time.monotonic()
    time.sleep(3)
    while time.monotonic() - t0 < timeout:
        try:
            r = aws("ssm", "get-command-invocation", "--command-id", cid, "--instance-id", instancia)
        except ErrorAws as e:
            if "InvocationDoesNotExist" not in e.stderr:
                raise
            time.sleep(3)
            continue
        if r["Status"] not in ("Pending", "InProgress", "Delayed"):
            return r["Status"], r.get("StandardOutputContent", ""), r.get("StandardErrorContent", "")
        time.sleep(3)
    raise Fallo(f"el comando por SSM no terminó en {dur(timeout)}")


def prueba_respaldo():
    c, d = salidas(PILA_COMPUTO), salidas(PILA_DATOS)
    instancia, bucket = c.get("IdInstanciaA"), d.get("BucketNombre")
    if not instancia or not bucket:
        raise Fallo("faltan IdInstanciaA o BucketNombre (hacen falta las pilas de cómputo y datos)")
    base = "bash /opt/nodo-ruta/repo/despliegue/aws"
    if SIMULAR:
        log(f"   [simular] por SSM en {instancia}: {base}/respaldar.sh y luego {base}/datos.sh comprobar <último _manual.dump>")
        return
    estado, salida, error = ssm_ejecutar(instancia, f"{base}/respaldar.sh")
    log(f"   respaldar.sh: {estado}\n{salida.strip()}\n{error.strip()}".rstrip())
    if estado != "Success":
        raise Fallo("el respaldo a S3 falló")
    clave = aws("s3api", "list-objects-v2", "--bucket", bucket, "--prefix", "respaldos/", "--query",
                "sort_by(Contents[?ends_with(Key, '_manual.dump')], &LastModified)[-1].Key")
    if not isinstance(clave, str) or not re.fullmatch(r"respaldos/[A-Za-z0-9_]+\.dump", clave):
        raise Fallo(f"no encontré el respaldo recién creado en s3://{bucket}/respaldos/ ({clave!r})")
    log(f"   respaldo en S3: {clave}")
    estado, salida, error = ssm_ejecutar(instancia, f"{base}/datos.sh comprobar {clave}")
    log(f"   datos.sh comprobar: {estado}\n{salida.strip()}\n{error.strip()}".rstrip())
    if estado != "Success" or "COMPROBADO" not in salida:
        raise Fallo("la comprobación del respaldo (SHA-256 e índice de pg_restore) falló")


# ---------------------------------------------------------------- destruir

def vaciar_bucket(bucket):
    """Borra objetos, versiones y marcas de borrado (de 1000 en 1000). Tolera un bucket inexistente."""
    total = 0
    while True:
        r = aws_si_existe("s3api", "list-object-versions", "--bucket", bucket, "--max-items", "1000") or {}
        objetos = [{"Key": v["Key"], "VersionId": v["VersionId"]}
                   for v in (r.get("Versions") or []) + (r.get("DeleteMarkers") or [])]
        if not objetos:
            log(f"   bucket {bucket}: vacío ({total} objetos y versiones borrados)")
            return
        if SIMULAR:
            log(f"   [simular] se borrarían {len(objetos)}{'+' if r.get('NextToken') else ''} versiones de {bucket}")
            return
        with archivo_privado(json.dumps({"Objects": objetos, "Quiet": True})) as ruta:
            res = aws("s3api", "delete-objects", "--bucket", bucket, "--delete", f"file://{ruta}", lectura=False)
        if res and res.get("Errors"):
            raise Fallo(f"no pude borrar objetos de {bucket}: {res['Errors'][:3]}")
        total += len(objetos)


def revision_directa(region):
    """Plan B cuando la política de la organización (SCP) niega tag:GetResources en esa región.

    En us-east-1 solo interesa CloudFront (distribuciones cuyo comentario empieza por nodo-ruta-);
    en us-east-2, las pilas nodo-ruta-* y los buckets nodo-ruta-*."""
    if region == REGION_GLOBAL:
        r = aws("cloudfront", "list-distributions", "--query",
                "DistributionList.Items[?starts_with(Comment, 'nodo-ruta-')].[Id,Comment]", region=region) or []
        return [f"cloudfront:distribution/{i} ({c})" for i, c in r]
    pilas = aws("cloudformation", "describe-stacks", "--query", "Stacks[?starts_with(StackName, 'nodo-ruta-')].StackName") or []
    buckets = aws("s3api", "list-buckets", "--query", "Buckets[?starts_with(Name, 'nodo-ruta-')].Name") or []
    return [f"cloudformation:stack/{p}" for p in pilas] + [f"s3:::{b}" for b in buckets]


def recursos_etiquetados(conservar_secretos=False):
    """(pendientes, permanentes) con la etiqueta proyecto=nodo-ruta, en us-east-2 y us-east-1."""
    pendientes, permanentes = [], []
    permitidos = PERMANENTES + ((":parameter/nodo-ruta/",) if conservar_secretos else ())
    for region in (REGION, REGION_GLOBAL):
        try:
            arns = aws("resourcegroupstaggingapi", "get-resources", "--tag-filters", "Key=proyecto,Values=nodo-ruta",
                       "--query", "ResourceTagMappingList[].ResourceARN", region=region) or []
        except ErrorAws as e:
            if "AccessDenied" not in e.stderr:
                raise
            log(f"   AVISO: la política de la organización niega tag:GetResources en {region}; se usa la revisión directa")
            arns = revision_directa(region)
        for arn in arns:
            (permanentes if any(p in arn for p in permitidos) else pendientes).append(f"{arn}  [{region}]")
    return pendientes, permanentes


def restos_esperados(pendientes):
    """Separa de 'pendientes' lo que AWS limpia solo y no es del despliegue.

    - Instancias EC2 en estado terminated (salen del índice de etiquetas en ~1 h).
    - Snapshots automáticos de RDS (arn ...:snapshot:rds:...): no se pueden borrar a mano y RDS los
      elimina cuando vence su retención; quedan como pendiente de verificar.
    Devuelve (pendientes_reales, esperados)."""
    ids = [p.split("instance/")[1].split()[0] for p in pendientes if ":instance/" in p]
    terminadas = set()
    for i in ids:
        try:      # una vez purgada, EC2 ya no la lista (o responde NotFound): solo queda su rastro en el índice
            vivas = aws("ec2", "describe-instances", "--instance-ids", i, "--query",
                        "Reservations[].Instances[?State.Name!='terminated'].InstanceId[]") or []
        except ErrorAws as e:
            if "NotFound" not in e.stderr:
                continue                           # sin dato: se deja como pendiente
            vivas = []
        if not vivas:
            terminadas.add(i)
    reales, esperados = [], []
    for p in pendientes:
        if ":snapshot:rds:" in p or any(f":instance/{i}" in p for i in terminadas):
            esperados.append(p)
        else:
            reales.append(p)
    return reales, esperados


def verificar_destruccion(conservar_secretos):
    pendientes, permanentes = recursos_etiquetados(conservar_secretos)
    pendientes, esperados = restos_esperados(pendientes)
    if SIMULAR:
        log(f"   [simular] hoy hay {len(pendientes)} recursos con {ETIQUETA}; tras destruir se exigiría 0")
        return
    for intento in range(1, 6):
        if not pendientes:
            break
        if intento < 5:
            log(f"   quedan {len(pendientes)} recursos en el índice de etiquetas; reintento en 20 s (el índice tarda en actualizarse)")
            time.sleep(20)
            pendientes, permanentes = recursos_etiquetados(conservar_secretos)
            pendientes, esperados = restos_esperados(pendientes)
    for p in permanentes:
        log(f"   permanente (a propósito): {p}")
    for p in esperados:
        log(f"   resto esperado (AWS lo limpia solo; verificar más tarde): {p}")
    if pendientes:
        for p in pendientes:
            log(f"   PENDIENTE: {p}")
        raise Fallo(f"quedan {len(pendientes)} recursos con {ETIQUETA}")
    log(f"   no queda ningún recurso con {ETIQUETA} en {REGION} ni en {REGION_GLOBAL}")


# ---------------------------------------------------------------- subcomandos

def cmd_estado(a):
    i = aws("sts", "get-caller-identity")
    log(f"Cuenta {i['Account']}  {i['Arn']}  región {REGION}")
    pilas = [p for p in (aws("cloudformation", "describe-stacks") or {}).get("Stacks", [])
             if p["StackName"].startswith("nodo-ruta-")]
    log("== Pilas nodo-ruta-*")
    if not pilas:
        log("   (no hay pilas)")
    for p in sorted(pilas, key=lambda p: p["StackName"]):
        log(f"   {p['StackName']:<20} {p['StackStatus']}")
    salida_de = {p["StackName"]: {o["OutputKey"]: o["OutputValue"] for o in p.get("Outputs", [])} for p in pilas}
    log("== URLs")
    for nombre, clave, texto in ((PILA_FRONT, "UrlFront", "CloudFront (HTTPS)"), (PILA_COMPUTO, "UrlAlb", "ALB directo (HTTP)")):
        log(f"   {texto:<20} {salida_de.get(nombre, {}).get(clave) or '(no disponible)'}")
    log("== Salud del target group")
    arn = salida_de.get(PILA_COMPUTO, {}).get("ArnGrupoDestino")
    if arn:
        try:
            r = aws("elbv2", "describe-target-health", "--target-group-arn", arn)
            for t in r["TargetHealthDescriptions"]:
                log(f"   {t['Target']['Id']}: {t['TargetHealth']['State']} {t['TargetHealth'].get('Reason', '')}".rstrip())
            if not r["TargetHealthDescriptions"]:
                log("   (sin destinos registrados)")
        except ErrorAws as e:
            log(f"   no se pudo leer ({e.stderr.strip()[:120]})")
    else:
        log("   (no hay target group)")
    log("== Parámetros SSM (solo nombres; nunca los valores)")
    r = aws("ssm", "describe-parameters", "--parameter-filters", "Key=Name,Option=BeginsWith,Values=/nodo-ruta/")
    presentes = {x["Name"] for x in (r or {}).get("Parameters", [])}
    for n in (SSM_CLAVE_DB, SSM_CLAVE_ORIGEN):
        log(f"   {n:<32} {'presente' if n in presentes else 'falta'}")
    for n in sorted(presentes - {SSM_CLAVE_DB, SSM_CLAVE_ORIGEN}):
        log(f"   {n:<32} presente (extra)")
    pendientes, _ = recursos_etiquetados()
    pendientes, _ = restos_esperados(pendientes)
    log(f"== Recursos con {ETIQUETA}: {len(pendientes)} (sin contar los permanentes)")
    for p in pendientes[:15]:
        log(f"   {p}")
    if len(pendientes) > 15:
        log(f"   ... y {len(pendientes) - 15} más")
    if any(n in salida_de for n in (PILA_DATOS, PILA_COMPUTO)):
        log("")
        log("COSTO: hay cómputo o datos (RDS, EC2, ALB) en la cuenta y consumen créditos (~USD 2 a 3 al día).")
        log("       Para destruir todo: python scripts/aws_nodo.py destruir")


def cmd_desplegar(a):
    with paso("1/7 Prechequeos"):
        i = aws("sts", "get-caller-identity")
        log(f"   cuenta {i['Account']}  {i['Arn']}  región {REGION} (fija)")
        for herramienta in ("git", "npm"):
            if not shutil.which(herramienta):
                raise Fallo(f"falta '{herramienta}' en el PATH (npm hace falta para construir el front en el paso 6)")
        sucios = comprobar_git()
        if sucios:
            for s in sucios:
                log(f"   cambios sin confirmar: {s}")
            if not a.permitir_sucio:
                raise Fallo("hay cambios sin confirmar en archivos que se despliegan; haz commit y push "
                            "(o usa --permitir-sucio bajo tu responsabilidad)")
        commit = resolver_commit(a.version)
        log(f"   commit a desplegar (existe en GitHub): {commit}")
        cabeza = git("rev-parse", "HEAD")
        if cabeza != commit:
            log(f"   AVISO: tu HEAD ({cabeza[:12]}) no es el commit a desplegar; las plantillas salen de tu carpeta y el código de las EC2 del commit")
        if git("cat-file", "-e", f"{commit}:despliegue/aws/datos.sh", tolerar=True) is None:
            log("   AVISO: ese commit no trae despliegue/aws/datos.sh; 'probar' fallará en la comprobación del respaldo")

    with paso("2/7 CidrAcceso"):
        cidr = validar_cidr(a.cidr) if a.cidr else ip_publica() + "/32"
        log(f"   CidrAcceso = {cidr} ({'argumento' if a.cidr else 'IP pública detectada con checkip.amazonaws.com'})")
        log("   Solo esa IP podrá usar el ALB y CloudFront; si cambia, repite 'desplegar --cidr NUEVA/32'.")

    with paso("3/7 Secretos en SSM"):
        asegurar_secreto(SSM_CLAVE_DB, 12)          # 24 caracteres hex: válidos para RDS
        asegurar_secreto(SSM_CLAVE_ORIGEN, 24)      # 48 caracteres hex: cumple ^[A-Za-z0-9]{32,128}$
        clave_origen = leer_secreto(SSM_CLAVE_ORIGEN)

    prefix = prefix_list_cloudfront()
    pares = {
        PILA_RED: [("CidrAcceso", cidr)] + ([("PrefixListCloudFront", prefix)] if prefix else []),
        PILA_DATOS: [],
        PILA_COMPUTO: [("VersionGit", commit), ("ClaveOrigen", clave_origen), ("CidrAcceso", cidr)],
        PILA_FRONT: [("ClaveOrigen", clave_origen), ("CidrAcceso", cidr)],
    }
    for n, (nombre, plantilla, previos) in enumerate(PILAS, 1):
        with paso(f"4.{n}/7 Pila {nombre}"):
            asegurar_pila(nombre, plantilla, pares[nombre], previos, a.permitir_reemplazo)
    del clave_origen, pares

    with paso("5/7 Destinos del balanceador healthy"):
        if SIMULAR:
            log("   [simular] se esperaría a que los 2 destinos del target group estén healthy (~15 min máximo)")
        else:
            esperar_destinos(salidas(PILA_COMPUTO)["ArnGrupoDestino"])

    with paso("6/7 Publicar el front"):
        cmd = [sys.executable, str(RAIZ / "scripts" / "publicar_front.py"), "--region", REGION]
        log(f"   {'[simular] ' if SIMULAR else ''}$ {mostrar(cmd)}")
        if not SIMULAR:
            proc = subprocess.run(cmd, cwd=RAIZ, text=True, capture_output=True, env=ENTORNO)
            for linea in (proc.stdout + proc.stderr).strip().splitlines():
                log(f"   | {linea}")
            if proc.returncode != 0:
                raise Fallo(f"publicar_front.py terminó con código {proc.returncode}")

    with paso("7/7 Prueba de humo"):
        if SIMULAR:
            log("   [simular] GET / (200 HTML), /pedidos (200 con 6 pedidos) y /health alternando entre las dos zonas")
        else:
            url = comprobar_servicio(a)
            log(f"   Listo: {url}")


def cmd_probar(a):
    with paso("1/2 Prueba de humo"):
        url = salidas(PILA_FRONT).get("UrlFront")
        if not url:
            raise Fallo("no hay pila nodo-ruta-front con UrlFront; despliega primero")
        if SIMULAR:
            log(f"   [simular] GET {url}/, /pedidos y /health")
        else:
            comprobar_servicio(a)
    with paso("2/2 Respaldo a S3 y comprobación (por SSM, sin pruebas destructivas)"):
        prueba_respaldo()
    log("   Las pruebas de caída de una instancia y de restauración siguen en infra/aws/PRUEBAS.md.")


def cmd_destruir(a):
    if not SIMULAR and not a.si:
        print("Esto borra TODO lo de Nodo Ruta en AWS: pilas, RDS, respaldos de S3"
              + ("." if a.conservar_secretos else " y los parámetros SSM."))
        try:
            respuesta = input("Escribe 'destruir' para continuar: ").strip()
        except EOFError:
            respuesta = ""
        if respuesta != "destruir":
            raise Fallo("cancelado (no se borró nada)")
    with paso("1/7 Identidad"):
        i = aws("sts", "get-caller-identity")
        log(f"   cuenta {i['Account']}  {i['Arn']}  región {REGION}")
    with paso("2/7 Front: vaciar bucket y borrar nodo-ruta-front"):
        bucket = salidas(PILA_FRONT).get("NombreBucket")
        if bucket:
            vaciar_bucket(bucket)
        borrar_pila(PILA_FRONT)
    with paso("3/7 Cómputo: borrar nodo-ruta-computo"):
        borrar_pila(PILA_COMPUTO)
    with paso("4/7 Datos: vaciar respaldos (con versiones) y borrar nodo-ruta-datos"):
        bucket = salidas(PILA_DATOS).get("BucketNombre")
        if bucket:
            vaciar_bucket(bucket)
        borrar_pila(PILA_DATOS)
    with paso("5/7 Red: borrar nodo-ruta-red"):
        borrar_pila(PILA_RED)
    with paso("6/7 Parámetros SSM"):
        if a.conservar_secretos:
            log("   --conservar-secretos: no se borran los parámetros")
        else:
            existentes = [n for n in (SSM_CLAVE_DB, SSM_CLAVE_ORIGEN) if ssm_existe(n)]
            if existentes:
                aws("ssm", "delete-parameters", "--names", *existentes, lectura=False)
            log(f"   {'se borrarían' if SIMULAR else 'borrados'}: {existentes or 'ninguno (no estaban)'}")
    with paso(f"7/7 Verificar que no queda nada con {ETIQUETA}"):
        verificar_destruccion(a.conservar_secretos)


# ---------------------------------------------------------------- principal

def resumen(inicio, ok):
    log("")
    log("Resumen" + (" (SIMULACIÓN: no se cambió nada)" if SIMULAR else ""))
    for nombre, seg, res in PASOS:
        log(f"   {res:<5} {dur(seg):>10}  {nombre}")
    log(f"   Duración total: {dur(time.monotonic() - inicio)}  ->  {'ÉXITO' if ok else 'FALLO'}")


def guardar_bitacora(ruta):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(BITACORA) + "\n", encoding="utf-8")
    print(f"Bitácora guardada en {ruta}")


def main():
    global SIMULAR, AWS
    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument("--simular", action="store_true", default=argparse.SUPPRESS,
                       help="solo lecturas: muestra los comandos que ejecutaría")
    comun.add_argument("--evidencia", metavar="PREFIJO", default=None,
                       help="guarda la bitácora en evidencias/<PREFIJO>_<acción>_<fecha>.txt (por ejemplo AWS09)")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simular", action="store_true", help="solo lecturas: muestra los comandos que ejecutaría")
    sub = ap.add_subparsers(dest="accion", required=True)
    sub.add_parser("estado", parents=[comun], help="pilas, URLs, salud, parámetros SSM y costo")
    d = sub.add_parser("desplegar", parents=[comun], help="despliega todo (idempotente)")
    d.add_argument("--cidr", help="IP o rango con acceso (por defecto, tu IP pública /32)")
    d.add_argument("--version", help="commit a desplegar (por defecto origin/main)")
    d.add_argument("--permitir-reemplazo", action="store_true",
                   help="acepta cambios que reemplazan recursos (EC2, grupos de seguridad...); por defecto se aborta")
    d.add_argument("--humo-remoto", action="store_true",
                   help="la prueba de humo se hace por SSM en las EC2 (automático dentro de GitHub Actions)")
    d.add_argument("--permitir-sucio", action="store_true", help="acepta cambios sin confirmar en archivos desplegados")
    p = sub.add_parser("probar", parents=[comun], help="prueba de humo y respaldo a S3 (sin pruebas destructivas)")
    p.add_argument("--humo-remoto", action="store_true",
                   help="la prueba de humo se hace por SSM en las EC2 (automático dentro de GitHub Actions)")
    x = sub.add_parser("destruir", parents=[comun], help="borra todo y verifica que no queda nada")
    x.add_argument("--si", action="store_true", help="no pide confirmación")
    x.add_argument("--conservar-secretos", action="store_true", help="no borra los parámetros SSM")
    a = ap.parse_args()
    SIMULAR = a.simular

    AWS = shutil.which("aws")
    if not AWS:
        sys.exit("No encuentro 'aws' en el PATH (instala AWS CLI v2).")
    if os.environ.get("AWS_REGION") not in (None, REGION) or os.environ.get("AWS_DEFAULT_REGION") not in (None, REGION):
        print(f"Aviso: se ignora la región del entorno; este script usa solo {REGION}.")
    ruta_evidencia = None
    if a.evidencia:
        nombre = {"estado": "estado", "desplegar": "despliegue", "probar": "prueba", "destruir": "destruccion"}[a.accion]
        ruta_evidencia = RAIZ / "evidencias" / f"{a.evidencia}_{nombre}_{datetime.date.today():%Y-%m-%d}.txt"
        if ruta_evidencia.exists():
            ap.error(f"{ruta_evidencia} ya existe; usa otro prefijo para conservar la evidencia anterior")
    inicio, ok = time.monotonic(), False
    log(f"aws_nodo.py {a.accion}{' (simulación)' if SIMULAR else ''}  región {REGION}")
    try:
        {"estado": cmd_estado, "desplegar": cmd_desplegar, "probar": cmd_probar, "destruir": cmd_destruir}[a.accion](a)
        ok = True
    except Fallo as e:
        log(f"ERROR: {e}")
    except ErrorAws as e:
        log(f"ERROR del AWS CLI: {e}")
        if "Unable to locate credentials" in e.stderr or "expired" in e.stderr.lower():
            log("   Inicia sesión de nuevo (aws login / aws sso login) y repite.")
    except KeyboardInterrupt:
        log("Interrumpido por el usuario (las pilas en curso siguen en AWS: usa 'estado').")
    finally:
        if a.accion != "estado":
            resumen(inicio, ok)
        if ruta_evidencia:
            guardar_bitacora(ruta_evidencia)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
