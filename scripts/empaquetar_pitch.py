#!/usr/bin/env python3
"""Empaqueta la presentación y el guion en archivos únicos, sin la carpeta assets/.

- presentacion/pitch.html -> presentacion/index.html (la presentación)
- presentacion/guion.html -> presentacion/guion-unico.html (el guion; sus enlaces a pitch.html
  pasan a index.html, así que conviene enviar los dos archivos juntos)

Reemplaza cada referencia a assets/... (imágenes PNG y SVG) por un data URI en base64.

Uso:  python scripts/empaquetar_pitch.py
"""
import base64
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent / "presentacion"
ARCHIVOS = [("pitch.html", "index.html"), ("guion.html", "guion-unico.html")]
TIPOS = {".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def empaquetar(origen, destino):
    html = (RAIZ / origen).read_text(encoding="utf-8")
    if origen == "guion.html":
        html = html.replace("pitch.html", "index.html")
    usados = {}

    def a_data_uri(m):
        ruta = m.group(0)
        archivo = RAIZ / ruta
        tipo = TIPOS.get(archivo.suffix.lower())
        if tipo is None or not archivo.is_file():
            sys.exit(f"No se puede incrustar {ruta}: no existe o tipo no soportado")
        if ruta not in usados:
            usados[ruta] = f"data:{tipo};base64," + base64.b64encode(archivo.read_bytes()).decode("ascii")
        return usados[ruta]

    salida = re.sub(r"assets/[A-Za-z0-9_\-./]+\.(?:png|svg|jpe?g)", a_data_uri, html)
    sys.exit(f"{origen}: quedó alguna referencia a assets/ sin incrustar") if "assets/" in salida else None
    (RAIZ / destino).write_text(salida, encoding="utf-8")
    print(f"presentacion/{destino}: {len(usados)} recursos incrustados, {(RAIZ / destino).stat().st_size / 1024:.0f} KB")


def main():
    for origen, destino in ARCHIVOS:
        empaquetar(origen, destino)


if __name__ == "__main__":
    main()
