import http.client
import itertools
import json
import os
import signal
import socket
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA = Path(os.environ.get("DATA_PATH", "pedidos.json"))
# Sin INSTANCE_ID (p. ej. réplicas en la nube que comparten variables) se usa el hostname.
INSTANCE = os.environ.get("INSTANCE_ID") or socket.gethostname()
# Versión del código desplegado; la fija el build (--build-arg APP_VERSION=...).
APP_VERSION = os.environ.get("APP_VERSION", "dev")
# Modo microservicios (staging): si PEDIDOS_URL está definida, los datos se piden
# por HTTP al servicio de pedidos (que los lee de PostgreSQL). Si no, se lee el
# archivo JSON como en la versión original.
PEDIDOS_URL = urllib.parse.urlsplit(os.environ.get("PEDIDOS_URL", ""))
PEDIDOS_TIMEOUT = float(os.environ.get("PEDIDOS_TIMEOUT", "2"))
_turno = itertools.count()


def leer_datos():
    """Devuelve (datos, origen). origen identifica la réplica del servicio de pedidos."""
    if not PEDIDOS_URL.hostname:
        return json.loads(DATA.read_text(encoding="utf-8")), None
    # El nombre (alias de red "pedidos") resuelve a la IP de cada réplica viva.
    # Se reparten por turnos y, si una no responde o devuelve error, se prueba la
    # siguiente. Se usa el alias y no un nombre por réplica porque resolver el
    # nombre de un contenedor que se está recreando tarda varios segundos.
    puerto = PEDIDOS_URL.port or 80
    ips = sorted({a[4][0] for a in socket.getaddrinfo(PEDIDOS_URL.hostname, puerto, type=socket.SOCK_STREAM)})
    inicio, ultimo_error = next(_turno), None
    for i in range(len(ips)):
        ip = ips[(inicio + i) % len(ips)]
        conn = http.client.HTTPConnection(ip, puerto, timeout=PEDIDOS_TIMEOUT)
        try:
            conn.request("GET", "/pedidos", headers={"Host": PEDIDOS_URL.netloc})
            r = conn.getresponse()
            cuerpo = r.read()
            if r.status != 200:
                raise OSError(f"{ip} respondió {r.status}")
            datos = json.loads(cuerpo)
            origen = {"instancia": datos.get("instancia"), "version_app": datos.get("version_app"),
                      "origen_datos": datos.get("origen_datos")}
            if datos.get("origen_datos") == "cache":
                origen["antiguedad_cache_s"] = datos.get("antiguedad_cache_s")
            return {"version": datos.get("version"), "pedidos": datos.get("pedidos")}, origen
        except (OSError, ValueError, http.client.HTTPException) as e:
            ultimo_error = e
        finally:
            conn.close()
    raise OSError(f"servicio de pedidos no disponible: {ultimo_error}")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route not in ("/", "/health", "/pedidos"):
            status, response = 404, {"error": "Ruta no disponible", "instancia": INSTANCE}
        else:
            try:
                data, origen = leer_datos()
                if not isinstance(data.get("pedidos"), list):
                    raise ValueError("Formato de datos inválido")
                status = 200
                if route == "/pedidos":
                    response = {"instancia": INSTANCE, "version_app": APP_VERSION, **data}
                elif route == "/health":
                    response = {"estado": "ok", "instancia": INSTANCE, "version_app": APP_VERSION, "version_datos": data.get("version")}
                else:
                    response = {"servicio": "Nodo Ruta - caso ficticio", "instancia": INSTANCE, "version_app": APP_VERSION, "rutas": ["/health", "/pedidos"]}
                if origen:
                    response["servicio_datos"] = origen
                    if route == "/health" and origen.get("origen_datos") == "cache":
                        response["estado"] = "degradado"  # responde, pero con la copia en memoria
            except (OSError, ValueError, TypeError, AttributeError) as e:
                if PEDIDOS_URL.hostname:
                    self.log_error("%s", e)
                status, response = 503, {"estado": "error_datos", "instancia": INSTANCE, "version_app": APP_VERSION}
        payload = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        # Permite al frontend (Vite) consultar con VITE_API_URL en otro origen.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Accept, Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)

    # Apagado ordenado: al recibir SIGTERM (docker stop / despliegue) deja de
    # aceptar conexiones y termina las solicitudes en curso antes de salir.
    # Sin esto, Python como PID 1 ignora SIGTERM y Docker lo mata con SIGKILL.
    def apagar(signum, frame):
        print(f"Nodo Ruta: {INSTANCE} recibió señal {signum}, apagando ordenadamente", flush=True)
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, apagar)
    print(f"Nodo Ruta: {INSTANCE}, versión {APP_VERSION}, puerto {port}", flush=True)
    server.serve_forever()
    server.server_close()
    print(f"Nodo Ruta: {INSTANCE} detenida", flush=True)
