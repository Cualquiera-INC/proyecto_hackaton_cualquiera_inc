#!/bin/bash
# Operaciones sobre los datos de RDS desde una EC2 (se ejecuta como root, por SSM o a mano).
#   datos.sh verificar               version de los datos y cuantos pedidos hay
#   datos.sh comprobar <clave|ultimo>   baja el respaldo de S3 y verifica SHA-256 y contenido (pg_restore --list)
#   datos.sh alterar <clave|ultimo>     SIMULA un dano: DROP TABLE pedidos (exige un respaldo valido en S3)
#   datos.sh restaurar <clave|ultimo>   comprueba el respaldo, guarda uno "prerestauracion" y restaura de forma atomica
# <clave> es respaldos/<fecha>_manual.dump; "ultimo" toma el mas reciente que termina en _manual.dump.
# Solo datos sinteticos. Usa /etc/nodo-ruta.env (sin secretos) y la clave en /etc/nodo-ruta/db_password.
set -euo pipefail
export HOME="${HOME:-/root}"
source /etc/nodo-ruta.env
AQUI="$(cd "$(dirname "$0")" && pwd)"
PG_IMG=postgres:17.6-alpine
DIR=/var/tmp/nodo-ruta-datos
install -d -m 700 "$DIR"
trap 'rm -rf "$DIR"/*' EXIT
CONEXION=(-h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME")

# Ejecuta una herramienta de PostgreSQL 17 (psql, pg_restore...) contra RDS dentro de un contenedor.
pg() {
  docker run --rm -e PGCLIENTENCODING=UTF8 -e PGPASSWORD="$(cat /etc/nodo-ruta/db_password)" -v "$DIR:$DIR" "$PG_IMG" "$@"
}

resolver() {   # deja la clave de S3 en KEY y el nombre del archivo en BASE
  KEY="$1"
  if [ "$KEY" = ultimo ]; then
    KEY=$(aws s3api list-objects-v2 --region "$REGION" --bucket "$BUCKET" --prefix respaldos/ \
      --query 'sort_by(Contents[?ends_with(Key, `_manual.dump`)], &LastModified)[-1].Key' --output text 2>/dev/null || true)
  fi
  [[ "$KEY" =~ ^respaldos/[A-Za-z0-9_]+\.dump$ ]] || { echo "Clave invalida o sin respaldos: $KEY" >&2; exit 1; }
  BASE="${KEY##*/}"
}

verificar() {
  pg psql "${CONEXION[@]}" -v ON_ERROR_STOP=1 -tA -F ' ' -c \
    "SELECT 'version_datos=' || (SELECT valor FROM metadatos WHERE clave = 'version') || ' pedidos=' || (SELECT count(*) FROM pedidos)" \
    || echo "La tabla pedidos no existe o la base no responde"
}

comprobar() {
  resolver "$1"
  aws s3 cp --only-show-errors --region "$REGION" "s3://$BUCKET/$KEY" "$DIR/$BASE"
  aws s3 cp --only-show-errors --region "$REGION" "s3://$BUCKET/${KEY%.dump}.sha256" "$DIR/${BASE%.dump}.sha256"
  local esperado real
  esperado=$(tr -d '[:space:]' < "$DIR/${BASE%.dump}.sha256")
  real=$(sha256sum "$DIR/$BASE" | cut -d' ' -f1)
  [ "$esperado" = "$real" ] || { echo "SHA-256 NO coincide en $KEY: esperado $esperado, real $real" >&2; exit 1; }
  pg pg_restore --list "$DIR/$BASE" > "$DIR/lista.txt"
  grep -q 'TABLE DATA public pedidos' "$DIR/lista.txt" || { echo "$KEY no contiene los datos de pedidos" >&2; exit 1; }
  echo "COMPROBADO $KEY: $(stat -c %s "$DIR/$BASE") bytes, sha256 $real, $(grep -vc '^;' "$DIR/lista.txt") objetos en el indice"
}

case "${1:-}" in
  verificar) verificar ;;
  comprobar) comprobar "${2:?falta la clave o ultimo}" ;;
  alterar)
    comprobar "${2:?falta la clave o ultimo}"   # sin respaldo valido no se toca nada
    pg psql "${CONEXION[@]}" -v ON_ERROR_STOP=1 -c "DROP TABLE pedidos"
    echo "Tabla pedidos eliminada (dano simulado). El /health del servicio debe devolver 503."
    ;;
  restaurar)
    comprobar "${2:?falta la clave o ultimo}"
    bash "$AQUI/respaldar.sh" prerestauracion   # copia del estado actual, por si algo sale mal
    pg pg_restore --clean --if-exists --single-transaction --no-owner "${CONEXION[@]}" "$DIR/$BASE"
    echo "Restaurado desde $KEY"
    verificar
    ;;
  *) echo "Uso: datos.sh verificar | comprobar|alterar|restaurar <clave|ultimo>" >&2; exit 2 ;;
esac
