import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA = Path(os.environ.get("DATA_PATH", "pedidos.json"))
INSTANCE = os.environ.get("INSTANCE_ID", "instancia-ejemplo")

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
                    response = {"instancia": INSTANCE, **data}
                elif route == "/health":
                    response = {"estado": "ok", "instancia": INSTANCE, "version_datos": data.get("version")}
                else:
                    response = {"servicio": "Nodo Ruta - caso ficticio", "instancia": INSTANCE, "rutas": ["/health", "/pedidos"]}
            except (OSError, ValueError, TypeError, AttributeError):
                status, response = 503, {"estado": "error_datos", "instancia": INSTANCE}
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
    print(f"Nodo Ruta: {INSTANCE}, puerto {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
