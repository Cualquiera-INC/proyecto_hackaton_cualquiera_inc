#!/bin/bash
# Respaldo manual: pg_dump (formato custom) de RDS hacia el bucket de S3, con su huella SHA-256.
# Se ejecuta en una EC2 (a mano o por SSM, como root): bash /opt/nodo-ruta/repo/despliegue/aws/respaldar.sh [etiqueta]
# La etiqueta (minusculas y numeros, por defecto "manual") queda en el nombre: <fecha>_<etiqueta>.dump
# Necesita /etc/nodo-ruta.env (con BUCKET) y el permiso s3:PutObject de la EC2 sobre respaldos/.
set -euo pipefail
export HOME="${HOME:-/root}"   # SSM RunShellScript no siempre define HOME
source /etc/nodo-ruta.env
ETIQUETA="${1:-manual}"
[[ "$ETIQUETA" =~ ^[a-z0-9]+$ ]] || { echo "Etiqueta invalida: solo minusculas y numeros" >&2; exit 1; }
PG_IMG=postgres:17.6-alpine
MARCA=$(date -u +%Y%m%d_%H%M%S)
# Carpeta propia (no /tmp): la monta el contenedor y el script debe verla igual desde SSM.
DIR=/var/tmp/nodo-ruta-respaldos
install -d -m 700 "$DIR"
ARCHIVO="$DIR/${MARCA}_${ETIQUETA}.dump"
trap 'rm -f "$ARCHIVO" "${ARCHIVO%.dump}.sha256"' EXIT
docker run --rm -e PGPASSWORD="$(cat /etc/nodo-ruta/db_password)" -v "$DIR:$DIR" "$PG_IMG" \
  pg_dump -Fc -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$ARCHIVO"
# Integridad antes de subir: pg_restore debe poder leer el indice del archivo y este debe incluir los pedidos.
# Excepcion: la copia "prerestauracion" guarda el estado actual tal cual, aunque este danado (sin pedidos);
# exigirle los pedidos impedia restaurar justo cuando hace falta (hallazgo de AWS06).
LISTA=$(docker run --rm -v "$DIR:$DIR:ro" "$PG_IMG" pg_restore --list "$ARCHIVO") \
  || { echo "El respaldo no se puede leer con pg_restore: no se sube" >&2; exit 1; }
if [ "$ETIQUETA" != prerestauracion ]; then
  grep -q 'TABLE DATA public pedidos' <<< "$LISTA" \
    || { echo "El respaldo no contiene los datos de pedidos: no se sube" >&2; exit 1; }
fi
sha256sum "$ARCHIVO" | cut -d' ' -f1 > "${ARCHIVO%.dump}.sha256"
aws s3 cp --only-show-errors --region "$REGION" "$ARCHIVO" "s3://$BUCKET/respaldos/${MARCA}_${ETIQUETA}.dump"
aws s3 cp --only-show-errors --region "$REGION" "${ARCHIVO%.dump}.sha256" "s3://$BUCKET/respaldos/${MARCA}_${ETIQUETA}.sha256"
echo "Respaldo subido: s3://$BUCKET/respaldos/${MARCA}_${ETIQUETA}.dump ($(stat -c %s "$ARCHIVO") bytes, sha256 $(cat "${ARCHIVO%.dump}.sha256"))"
