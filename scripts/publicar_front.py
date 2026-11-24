#!/usr/bin/env python3
"""Construye la interfaz web y la publica en el bucket S3 de la pila nodo-ruta-front.

Solo biblioteca estandar. Necesita Node (npm) y la AWS CLI con credenciales activas.
Pasos: npm ci, npm run build (VITE_API_URL vacio = mismo origen), s3 sync de assets/ (cache largo),
s3 sync del resto (no-cache) e invalidacion de /index.html y /.

Uso:
    python3 scripts/publicar_front.py
    python3 scripts/publicar_front.py --pila nodo-ruta-front --region us-east-2
    python3 scripts/publicar_front.py --sin-build      (reusa frontend-nodo/dist)
    python3 scripts/publicar_front.py --simular        (muestra los comandos, no toca AWS)
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FRONT = RAIZ / "frontend-nodo"
DIST = FRONT / "dist"


def ejecutar(cmd, cwd=None, env=None, simular=False, solo_lectura=False):
    print("$ " + " ".join(cmd))
    if simular and not solo_lectura:
        return ""
    res = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=solo_lectura)
    if res.returncode != 0:
        if solo_lectura:
            print(res.stderr, file=sys.stderr)
        sys.exit(f"Fallo (codigo {res.returncode}): {' '.join(cmd)}")
    return res.stdout.strip() if solo_lectura else ""


def salida_pila(aws, pila, region, clave):
    return ejecutar(
        [aws, "cloudformation", "describe-stacks", "--region", region, "--stack-name", pila,
         "--query", f"Stacks[0].Outputs[?OutputKey=='{clave}'].OutputValue", "--output", "text"],
        solo_lectura=True,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pila", default="nodo-ruta-front")
    ap.add_argument("--region", default="us-east-2")
    ap.add_argument("--sin-build", action="store_true")
    ap.add_argument("--simular", action="store_true", help="no sube nada ni invalida; solo lee las salidas de la pila")
    a = ap.parse_args()

    aws = shutil.which("aws")
    npm = shutil.which("npm")
    if not aws or not npm:
        sys.exit("Faltan herramientas: se necesita 'aws' y 'npm' en el PATH.")

    bucket = salida_pila(aws, a.pila, a.region, "NombreBucket")
    dist_id = salida_pila(aws, a.pila, a.region, "IdDistribucion")
    if not bucket or not dist_id or "None" in (bucket, dist_id):
        sys.exit(f"No pude leer NombreBucket/IdDistribucion de la pila {a.pila}.")
    print(f"Bucket: {bucket}  Distribucion: {dist_id}")

    if not a.sin_build:
        env = dict(os.environ, VITE_API_URL="")
        ejecutar([npm, "ci"], cwd=FRONT, env=env, simular=a.simular)
        ejecutar([npm, "run", "build"], cwd=FRONT, env=env, simular=a.simular)
    if not (DIST / "index.html").is_file():
        if not a.simular:
            sys.exit(f"No existe {DIST / 'index.html'}; construye primero.")

    destino = f"s3://{bucket}"
    # Los archivos de assets/ llevan hash en el nombre: se pueden cachear un anio.
    ejecutar([aws, "s3", "sync", str(DIST / "assets"), f"{destino}/assets", "--region", a.region, "--delete",
              "--cache-control", "public,max-age=31536000,immutable"], simular=a.simular)
    # index.html y el logo conservan el nombre: el navegador debe revalidar siempre.
    ejecutar([aws, "s3", "sync", str(DIST), destino, "--region", a.region, "--delete",
              "--exclude", "assets/*", "--cache-control", "no-cache"], simular=a.simular)
    ejecutar([aws, "cloudfront", "create-invalidation", "--distribution-id", dist_id,
              "--paths", "/index.html", "/"], simular=a.simular)
    print("Listo." if not a.simular else "Simulacion terminada (no se subio nada).")


if __name__ == "__main__":
    main()
