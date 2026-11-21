import json
import os
import signal
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA = Path(os.environ.get("DATA_PATH", "pedidos.json"))
# Sin INSTANCE_ID (p. ej. réplicas en la nube que comparten variables) se usa el hostname.
INSTANCE = os.environ.get("INSTANCE_ID") or socket.gethostname()
# Versión del código desplegado; la fija el build (--build-arg APP_VERSION=...).
APP_VERSION = os.environ.get("APP_VERSION", "dev")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route not in ("/", "/health", "/pedidos"):
            status, response = 404, {"error": "Ruta no disponible", "instancia": INSTANCE}
        else:
            try:
                data = json.loads(DATA.read_text(encoding="utf-8"))
                if not isinstance(data.get("pedidos"), list):
                    raise ValueError("Formato de datos inválido")
                status = 200
                if route == "/pedidos":
                    response = {"instancia": INSTANCE, "version_app": APP_VERSION, **data}
                elif route == "/health":
                    response = {"estado": "ok", "instancia": INSTANCE, "version_app": APP_VERSION, "version_datos": data.get("version")}
                else:
                    response = {"servicio": "Nodo Ruta - caso ficticio", "instancia": INSTANCE, "version_app": APP_VERSION, "rutas": ["/health", "/pedidos"]}
            except (OSError, ValueError, TypeError, AttributeError):
                status, response = 503, {"estado": "error_datos", "instancia": INSTANCE, "version_app": APP_VERSION}
        payload = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

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
