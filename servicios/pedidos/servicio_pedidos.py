"""Microservicio de pedidos: expone por HTTP los pedidos guardados en PostgreSQL.

Rutas (solo lectura):
  /health   200 si hay datos que servir ("ok" o "degradado"); 503 si no
  /pedidos  {"version", "pedidos": [...]} con el mismo formato que pedidos.json

Lo consumen app1 y app2 (variable PEDIDOS_URL). Vive en la red interna "datos"
y no publica puertos.

Cómo tolera los fallos de la base:
  - Las consultas HTTP NUNCA esperan a la base. Un hilo lee PostgreSQL cada
    REFRESCO_S segundos (1 por defecto) y guarda el resultado en memoria; cada
    consulta responde desde esa copia al instante. Si la base se cae o se vuelve
    lenta, quien consulta no lo nota (medido: STG09 y STG10).
  - DB_HOST apunta a un alias que resuelve al primario y a la réplica; si una
    base no responde, el hilo lee de la otra (STG08).
  - Si ninguna base responde, se sigue sirviendo la última lectura correcta,
    marcada "origen_datos": "cache", hasta CACHE_MAX_S segundos (300).
  - Un error EN LOS DATOS (p. ej. la tabla no existe) borra la copia y responde
    503: un daño no se tapa, se detecta y se restaura desde un respaldo.

Configuración por variables de entorno:
  DB_HOST, DB_PORT, DB_NAME, DB_USER    conexión a PostgreSQL
  DB_PASSWORD_FILE (o DB_PASSWORD)      contraseña; se prefiere el archivo (Docker secret)
  REFRESCO_S, CACHE_MAX_S               cada cuánto se lee la base y antigüedad máxima de la copia
  INSTANCE_ID, APP_VERSION, PORT        identificación y puerto (8081)
"""
import json
import os
import signal
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

INSTANCE = os.environ.get("INSTANCE_ID") or socket.gethostname()
APP_VERSION = os.environ.get("APP_VERSION", "dev")
REFRESCO_S = float(os.environ.get("REFRESCO_S", "1"))
CACHE_MAX_S = float(os.environ.get("CACHE_MAX_S", "300"))
# Si la última lectura correcta es más antigua que esto, la copia se marca como "cache".
FRESCURA_S = max(3.0, 3 * REFRESCO_S)


def contrasena():
    archivo = os.environ.get("DB_PASSWORD_FILE")
    if archivo:
        return Path(archivo).read_text(encoding="utf-8").strip()
    return os.environ.get("DB_PASSWORD", "")


pool = ConnectionPool(
    kwargs={
        "host": os.environ.get("DB_HOST", "pg-lectura"),
        # Prueba las direcciones del alias (primario y réplica) en orden aleatorio:
        # reparte la carga y, si una no responde, pasa a la siguiente.
        "load_balance_hosts": "random",
        "port": int(os.environ.get("DB_PORT", "5432")),
        "dbname": os.environ.get("DB_NAME", "nodo_ruta"),
        "user": os.environ.get("DB_USER", "cualquieraInc"),
        "password": contrasena(),
        "connect_timeout": 2,
        "application_name": f"servicio-pedidos-{INSTANCE}",
        # El servicio solo consulta: cualquier escritura falla en la propia base.
        # Una consulta que tarde más de 2 s se cancela.
        "options": "-c default_transaction_read_only=on -c statement_timeout=2000",
    },
    min_size=1,
    max_size=2,                             # solo lee el hilo de refresco
    timeout=5,                              # espera máxima por una conexión libre
    check=ConnectionPool.check_connection,  # descarta conexiones muertas (p. ej. tras reiniciar la base)
    open=False,
    name=f"pedidos-{INSTANCE}",
)


def leer_base():
    with pool.connection() as conn:
        fila = conn.execute("SELECT valor FROM metadatos WHERE clave = 'version'").fetchone()
        pedidos = conn.execute("SELECT id, zona, estado FROM pedidos ORDER BY id").fetchall()
    if not fila:
        raise ValueError("Falta la versión de los datos en metadatos")
    return fila[0], [{"id": i, "zona": z, "estado": e} for i, z, e in pedidos]


class SinDatos(Exception):
    pass


# Copia en memoria. "momento" es la hora (monotonic) de la última lectura correcta.
_copia = {"version": None, "pedidos": None, "momento": None, "problema": None, "dano_datos": False}
_lock = threading.Lock()
_parar = threading.Event()


def refrescar():
    """Hilo de fondo: lee la base cada REFRESCO_S y actualiza la copia en memoria."""
    ultimo_problema = None
    while not _parar.is_set():
        problema = None
        try:
            version, pedidos = leer_base()
            with _lock:
                _copia.update(version=version, pedidos=pedidos, momento=time.monotonic(),
                              problema=None, dano_datos=False)
        except psycopg.OperationalError as e:
            # La base no responde (caída, reinicio, red, consulta cancelada): se
            # conserva la última copia correcta.
            problema = f"base no disponible: {type(e).__name__}"
            with _lock:
                _copia.update(problema=problema, dano_datos=False)
        except (psycopg.Error, ValueError) as e:
            # Los datos están dañados: se descarta la copia para no ocultarlo.
            problema = f"datos dañados: {type(e).__name__}"
            with _lock:
                _copia.update(version=None, pedidos=None, momento=None, problema=problema, dano_datos=True)
        if problema != ultimo_problema:  # solo se registran los cambios de estado
            print(f"Servicio pedidos: {INSTANCE} {problema or 'lectura de la base correcta'}", flush=True)
            ultimo_problema = problema
        _parar.wait(REFRESCO_S)


def obtener_datos():
    """Devuelve (version, pedidos, origen) desde la copia en memoria, sin tocar la base."""
    with _lock:
        c = dict(_copia)
    if c["dano_datos"]:
        raise SinDatos(c["problema"])
    if c["momento"] is None:
        raise SinDatos(c["problema"] or "todavía no hay una lectura de la base")
    edad = time.monotonic() - c["momento"]
    if edad > CACHE_MAX_S:
        raise SinDatos(f"la última lectura correcta tiene {edad:.0f} s ({c['problema']})")
    if c["problema"] is None and edad <= FRESCURA_S:
        origen = {"origen_datos": "base"}
    else:
        origen = {"origen_datos": "cache", "antiguedad_cache_s": round(edad, 1)}
    return c["version"], c["pedidos"], origen


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = self.path.split("?", 1)[0]
        base = {"instancia": INSTANCE, "version_app": APP_VERSION}
        if route not in ("/health", "/pedidos"):
            status, response = 404, {"error": "Ruta no disponible", **base}
        else:
            try:
                version, pedidos, origen = obtener_datos()
                status = 200
                if route == "/pedidos":
                    response = {**base, "version": version, "pedidos": pedidos, **origen}
                else:
                    estado = "ok" if origen["origen_datos"] == "base" else "degradado"
                    response = {"estado": estado, **base, "version_datos": version,
                                "total_pedidos": len(pedidos), **origen}
            except SinDatos:
                # El detalle queda en el registro del contenedor; al cliente no se le
                # exponen nombres de tablas ni mensajes de la base.
                status, response = 503, {"estado": "error_datos", **base}
        payload = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, formato, *args):
        # Las consultas de los healthchecks y de las apps son muchas; solo se
        # registran las que no terminan en 200.
        if len(args) > 1 and str(args[1]) != "200":
            super().log_message(formato, *args)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8081"))
    # Sin esperar: si la base aún no está lista, el pool reintenta en segundo plano
    # y mientras tanto /health responde 503.
    pool.open(wait=False)
    threading.Thread(target=refrescar, name="refresco", daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)

    def apagar(signum, frame):
        print(f"Servicio pedidos: {INSTANCE} recibió señal {signum}, apagando ordenadamente", flush=True)
        _parar.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, apagar)
    print(f"Servicio pedidos: {INSTANCE}, versión {APP_VERSION}, puerto {port}, "
          f"refresco cada {REFRESCO_S} s", flush=True)
    server.serve_forever()
    server.server_close()
    pool.close()
    print(f"Servicio pedidos: {INSTANCE} detenido", flush=True)
