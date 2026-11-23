#!/bin/bash
# Respaldo manual: pg_dump (formato custom) de RDS hacia el bucket de S3, con su huella SHA-256.
# Se ejecuta en una EC2 por SSM: sudo bash /opt/nodo-ruta/repo/despliegue/aws/respaldar.sh
# Necesita /etc/nodo-ruta.env (con BUCKET) y el permiso s3:PutObject de la EC2 sobre respaldos/.
set -euo pipefail
source /etc/nodo-ruta.env
MARCA=$(date -u +%Y%m%d_%H%M%S)
ARCHIVO="/tmp/${MARCA}_manual.dump"
docker run --rm -e PGPASSWORD="$(cat /etc/nodo-ruta/db_password)" -v /tmp:/tmp postgres:17.6-alpine \
  pg_dump -Fc -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$ARCHIVO"
sha256sum "$ARCHIVO" | cut -d' ' -f1 > "${ARCHIVO%.dump}.sha256"
aws s3 cp --region "$REGION" "$ARCHIVO" "s3://$BUCKET/respaldos/${MARCA}_manual.dump"
aws s3 cp --region "$REGION" "${ARCHIVO%.dump}.sha256" "s3://$BUCKET/respaldos/${MARCA}_manual.sha256"
rm -f "$ARCHIVO" "${ARCHIVO%.dump}.sha256"
echo "Respaldo subido: s3://$BUCKET/respaldos/${MARCA}_manual.dump"
