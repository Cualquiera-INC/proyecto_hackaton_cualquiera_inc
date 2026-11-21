"""Datos de Nodo Ruta en PostgreSQL (staging): preparar, respaldar, simular-error y restaurar.

  python scripts/datos.py preparar        crea despliegue/secretos/db_password.txt (no va al repositorio)
  python scripts/datos.py respaldar       pg_dump -> respaldos/<fecha>.dump + .sha256
  python scripts/datos.py simular-error   borra la tabla pedidos (exige un respaldo válido antes)
  python scripts/datos.py restaurar --respaldo respaldos/<archivo>.dump
  python scripts/datos.py verificar       muestra la versión de los datos y cuántos pedidos hay

La base corre en el contenedor "postgres" de despliegue/compose.yaml: pg_dump,
pg_restore y psql se ejecutan dentro de él, así que no hace falta instalar
PostgreSQL en el equipo. preparar toma la contraseña de NODO_DB_PASSWORD o la pide.
"""
from pathlib import Path
import argparse, datetime, getpass, hashlib, os, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "despliegue" / "compose.yaml"
SECRETO = ROOT / "despliegue" / "secretos" / "db_password.txt"
RESPALDOS = ROOT / "respaldos"
FIRMA_DUMP = b"PGDMP"  # cabecera de los archivos de pg_dump en formato custom
# Se usan las variables del propio contenedor para no repetir usuario y base aquí.
PSQL = 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" '


def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
# En UTC, igual que el servicio "respaldo", para que el orden por nombre sea el cronológico.
def stamp(): return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def inside(p, parent):
    p = p.resolve()
    if p == parent.resolve() or parent.resolve() not in p.parents:
        raise ValueError("La ruta debe estar dentro de " + str(parent))
    return p


def en_postgres(comando, entrada=None, salida=None):
    """Ejecuta un comando sh dentro del contenedor postgres del stack."""
    r = subprocess.run(["docker", "compose", "-f", str(COMPOSE), "exec", "-T", "postgres", "sh", "-c", comando],
                       stdin=entrada, stdout=salida if salida else subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        detalle = r.stderr.decode("utf-8", "replace").strip()
        raise ValueError(f"falló en el contenedor postgres ({r.returncode}): {detalle}")
    return r.stdout.decode("utf-8", "replace").strip() if r.stdout else ""


def validar_respaldo(p):
    huella = p.with_suffix(".sha256")
    if not huella.is_file():
        raise ValueError(f"Falta la huella {huella.name}")
    if digest(p) != huella.read_text(encoding="utf-8").strip():
        raise ValueError("El respaldo no coincide con su huella de integridad")
    with p.open("rb") as f:
        if f.read(5) != FIRMA_DUMP:
            raise ValueError("El archivo no es un respaldo de pg_dump (formato custom)")


def resumen():
    return en_postgres(PSQL + "-tA -F ' ' -c \"SELECT (SELECT valor FROM metadatos WHERE clave = 'version'), "
                       "(SELECT count(*) FROM pedidos)\"")


parser = argparse.ArgumentParser(description="Preparar, respaldar y restaurar los datos ficticios de Nodo Ruta en PostgreSQL.")
parser.add_argument("accion", choices=["preparar", "respaldar", "simular-error", "restaurar", "verificar"])
parser.add_argument("--respaldo", help="Archivo .dump dentro de respaldos/ (creado por este script o por el servicio respaldo)")
args = parser.parse_args()
try:
    if args.accion == "preparar":
        if SECRETO.exists():
            raise ValueError(f"{SECRETO.relative_to(ROOT)} ya existe; no se sobrescribe")
        clave = os.environ.get("NODO_DB_PASSWORD")
        if not clave:
            clave = getpass.getpass("Contraseña para la base de datos: ")
            if clave != getpass.getpass("Repítala: "):
                raise ValueError("Las contraseñas no coinciden")
        if not clave.strip():
            raise ValueError("La contraseña no puede estar vacía")
        SECRETO.parent.mkdir(parents=True, exist_ok=True)
        SECRETO.write_text(clave.strip(), encoding="utf-8")
        # Los contenedores (UID 70 y 10001) leen el archivo por un bind mount, por
        # eso necesita permiso de lectura para "otros". La carpeta no va al repositorio.
        os.chmod(SECRETO, 0o644)
        RESPALDOS.mkdir(exist_ok=True)
        print(f"Contraseña guardada en {SECRETO.relative_to(ROOT)} (ignorada por git).")
        print("Siguiente paso: python scripts/desplegar.py desplegar --version v1")
    elif args.accion == "respaldar":
        target = inside(RESPALDOS / (stamp() + ".dump"), RESPALDOS)
        target.parent.mkdir(exist_ok=True)
        tmp = target.with_suffix(".tmp")
        try:
            with tmp.open("wb") as f:
                en_postgres('pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"', salida=f)
            tmp.replace(target)
        finally:
            tmp.unlink(missing_ok=True)
        target.with_suffix(".sha256").write_text(digest(target), encoding="utf-8")
        validar_respaldo(target)
        print("Respaldo creado: " + target.relative_to(ROOT).as_posix())
    elif args.accion == "simular-error":
        validos = []
        for p in sorted(RESPALDOS.glob("*.dump")):
            try:
                validar_respaldo(p); validos.append(p)
            except (ValueError, OSError):
                pass
        if not validos:
            raise ValueError("No hay ningún respaldo válido. Ejecute antes: python scripts/datos.py respaldar")
        en_postgres(PSQL + '-c "DROP TABLE pedidos"')
        print("Tabla pedidos eliminada. /health debe devolver 503.")
        print("Respaldo más reciente: " + validos[-1].relative_to(ROOT).as_posix())
    elif args.accion == "restaurar":
        if not args.respaldo:
            raise ValueError("Indique --respaldo con la ruta del archivo .dump")
        source = inside(ROOT / args.respaldo, RESPALDOS)
        if source.suffix != ".dump":
            raise ValueError("Seleccione el archivo .dump del respaldo")
        validar_respaldo(source)
        # --single-transaction: o se restaura todo o no cambia nada.
        with source.open("rb") as f:
            en_postgres('pg_restore --clean --if-exists --single-transaction --no-owner '
                        '-U "$POSTGRES_USER" -d "$POSTGRES_DB"', entrada=f)
        version, total = resumen().split()
        print(f"Datos restaurados: version={version}, pedidos={total}. Verifique /health y /pedidos.")
    elif args.accion == "verificar":
        version, total = resumen().split()
        print(f"version={version} pedidos={total}")
except (ValueError, OSError) as e:
    parser.exit(1, "No se realizó la operación: " + str(e) + "\n")
