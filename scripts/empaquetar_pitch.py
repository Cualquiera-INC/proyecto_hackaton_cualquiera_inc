#!/usr/bin/env python3
"""Empaqueta presentacion/pitch.html en un solo archivo presentacion/index.html.

Reemplaza cada referencia a assets/... (imágenes PNG y SVG) por un data URI en base64,
para que la presentación se pueda enviar como un único archivo y abrir sin la carpeta assets/.

Uso:  python scripts/empaquetar_pitch.py
"""
import base64
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent / "presentacion"
ORIGEN = RAIZ / "pitch.html"
DESTINO = RAIZ / "index.html"
TIPOS = {".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def main():
    html = ORIGEN.read_text(encoding="utf-8")
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
    if "assets/" in salida:
        sys.exit("Quedó alguna referencia a assets/ sin incrustar")
    DESTINO.write_text(salida, encoding="utf-8")
    print(f"{DESTINO.relative_to(RAIZ.parent)}: {len(usados)} recursos incrustados, {DESTINO.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
