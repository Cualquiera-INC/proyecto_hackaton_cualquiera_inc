#!/bin/sh
# Réplica en espera (hot standby) de PostgreSQL: recibe los cambios del primario
# en tiempo real (streaming replication) y acepta consultas de solo lectura.
# Si el primario cae, el servicio de pedidos sigue leyendo de aquí.
#
# La primera vez (volumen vacío) copia la base completa del primario con
# pg_basebackup; las siguientes arranca directamente y se pone al día sola.
set -eu
export PGPASSWORD="$(cat /run/secrets/db_password)"

if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "Réplica: esperando al primario ($PRIMARIO)..."
    until pg_isready -h "$PRIMARIO" -U "$POSTGRES_USER" -q; do sleep 1; done
    # Restos de una copia anterior que no terminó (el volumen no tenía PG_VERSION).
    find "$PGDATA" -mindepth 1 -delete
    echo "Réplica: copiando la base del primario (pg_basebackup)..."
    # -R deja configurada la conexión al primario (standby.signal + primary_conninfo).
    pg_basebackup -h "$PRIMARIO" -U "$POSTGRES_USER" -D "$PGDATA" -R -X stream -c fast
    echo "Réplica: copia lista"
fi

chmod 700 "$PGDATA"
exec postgres -c hba_file=/etc/postgresql/pg_hba.conf
