-- Carga inicial en RDS: se ejecuta desde cada EC2 al arrancar y solo actua UNA vez.
-- Idempotente y segura si las dos EC2 arrancan a la vez:
--   1. un candado de sesion (pg_advisory_lock) hace que la segunda espere a la primera;
--   2. si la tabla pedidos ya existe no se toca nada (tampoco se pisa una restauracion);
--   3. esquema y datos van en una sola transaccion: no queda una carga a medias.
-- Solo datos sinteticos. Se usa con: psql -f cargar-inicial.sql (ver despliegue/aws/iniciar.sh).
\set ON_ERROR_STOP on
SELECT pg_advisory_lock(160001);
SELECT to_regclass('public.pedidos') IS NULL AS falta \gset
\if :falta
  BEGIN;
  \i /init/01-esquema.sql
  \i /init/02-datos-iniciales.sql
  COMMIT;
  \echo 'Carga inicial aplicada (esquema y 6 pedidos sinteticos).'
\else
  \echo 'La base ya tiene datos: no se carga nada.'
\endif
SELECT pg_advisory_unlock(160001);
