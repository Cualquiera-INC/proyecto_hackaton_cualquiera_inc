#!/bin/bash
# Arranca Nodo Ruta en una EC2: construye las 2 imagenes desde este repo, carga la base
# (una vez) y levanta los contenedores. Lo llama el user data de infra/aws/03-computo.yaml
# y se puede repetir a mano por SSM: sudo bash despliegue/aws/iniciar.sh
# Lee la configuracion de /etc/nodo-ruta.env (la escribe el user data; sin secretos).
set -euo pipefail
source /etc/nodo-ruta.env   # REGION VERSION DB_HOST DB_PORT DB_NAME DB_USER RUTA_CLAVE
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PG_IMG=postgres:17.6-alpine   # misma imagen que local (solo se usa su psql y pg_dump)

# --- Identificacion: zona + id de EC2 (IMDSv2, solo desde el anfitrion) ---
TOKEN=$(curl -sf -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
meta() { curl -sf -H "X-aws-ec2-metadata-token: $TOKEN" "http://169.254.169.254/latest/meta-data/$1"; }
INSTANCIA="$(meta placement/availability-zone)-$(meta instance-id)"
echo "Instancia: $INSTANCIA, version: $VERSION"

# --- Contrasena: de SSM a un archivo que solo lee el usuario del contenedor (10001) ---
install -d -m 755 /etc/nodo-ruta
aws ssm get-parameter --region "$REGION" --name "$RUTA_CLAVE" --with-decryption \
  --query Parameter.Value --output text | install -m 400 -o 10001 -g 10001 /dev/stdin /etc/nodo-ruta/db_password

# --- Imagenes (etiqueta = version, nunca latest) ---
docker build -q -t "nodo-ruta:$VERSION" --build-arg "APP_VERSION=$VERSION" "$REPO"
docker build -q -t "nodo-ruta-pedidos:$VERSION" --build-arg "APP_VERSION=$VERSION" "$REPO/servicios/pedidos"

# --- Carga inicial de la base (espera a que RDS responda) ---
for i in $(seq 1 60); do
  docker run --rm "$PG_IMG" pg_isready -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -U "$DB_USER" -q && break
  echo "Esperando a RDS ($i/60)..."; sleep 5
done
docker run --rm -e PGCLIENTENCODING=UTF8 -e PGPASSWORD="$(cat /etc/nodo-ruta/db_password)" \
  -v "$REPO/basedatos/init:/init:ro" -v "$REPO/basedatos/aws:/aws:ro" "$PG_IMG" \
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f /aws/cargar-inicial.sql

# --- Contenedores: pedidos (sin puertos publicados) y app (8080, solo hacia el ALB) ---
docker network inspect nodo >/dev/null 2>&1 || docker network create nodo >/dev/null
docker rm -f app pedidos >/dev/null 2>&1 || true
SALUD=(--health-interval 5s --health-timeout 3s --health-retries 3)
LOGS=(--log-opt max-size=10m --log-opt max-file=3)
docker run -d --name pedidos --network nodo --restart unless-stopped "${LOGS[@]}" "${SALUD[@]}" \
  --health-cmd "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/health', timeout=2).read()\"" \
  -e INSTANCE_ID="pedidos-$INSTANCIA" -e DB_HOST="$DB_HOST" -e DB_PORT="$DB_PORT" -e DB_NAME="$DB_NAME" -e DB_USER="$DB_USER" \
  -e DB_PASSWORD_FILE=/run/secrets/db_password -v /etc/nodo-ruta/db_password:/run/secrets/db_password:ro \
  "nodo-ruta-pedidos:$VERSION"
docker run -d --name app --network nodo --restart unless-stopped "${LOGS[@]}" "${SALUD[@]}" \
  --health-cmd "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).read()\"" \
  -p 8080:8080 -e INSTANCE_ID="$INSTANCIA" -e PEDIDOS_URL=http://pedidos:8081 \
  "nodo-ruta:$VERSION"
echo "Listo: $INSTANCIA sirviendo en :8080"
