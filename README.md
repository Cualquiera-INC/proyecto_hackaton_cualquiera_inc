# Nodo Ruta — solución local (MVP)

Caso ficticio de la hackatón EstudIA. Dos instancias de la app detrás de NGINX, datos fuera del contenedor y respaldo automático, todo con Docker Compose y **costo $0**.
Diagrama: [docs/diagrama_solucion_local.html](docs/diagrama_solucion_local.html) · Evidencias: [EVIDENCIAS.md](EVIDENCIAS.md) · Nube (solo diseño): [docs/nube-diseno.md](docs/nube-diseno.md)

| Servicio | Qué hace |
|---|---|
| `proxy` | NGINX, único puerto publicado: `127.0.0.1:8080`. Reparte entre app1 y app2 y reintenta en la otra si una falla (detección pasiva). |
| `app1`, `app2` | `app.py`, la misma imagen. Leen `data/pedidos.json` en solo lectura. El campo `instancia` dice quién respondió. |
| `respaldo` | Cada 5 min ejecuta `scripts/datos.py respaldar`, que valida el JSON y guarda la copia y su SHA-256 en `respaldos/`. |

## Recrear el despliegue
Requisitos: Python 3 y Docker Desktop **iniciado**. En Windows, `py` en lugar de `python` si es tu comando.
```text
python scripts/datos.py preparar
docker compose up -d --build
docker compose ps
```
Espera a que app1 y app2 aparezcan como `healthy`.

## Pruebas (guardan evidencia en `evidencias/`; usa un nombre de salida nuevo en cada repetición)
```text
# I01 acceso común
python scripts/verificar_servicio.py --esperadas app1,app2 --salida evidencias/I01_inicio.json
# I02 caída de app1
docker compose stop app1
python scripts/verificar_servicio.py --esperadas app2 --salida evidencias/I02_fallo_app1.json
# I03 recuperación
docker compose start app1
python scripts/verificar_servicio.py --esperadas app1,app2 --salida evidencias/I03_recupera_app1.json
# I04 recrear sin perder datos
docker compose up -d --force-recreate app1
python scripts/verificar_servicio.py --esperadas app1,app2 --salida evidencias/I04_recrear_app1.json
# I05 datos alterados -> 503 -> restaurar
python scripts/datos.py simular-error
python scripts/verificar_servicio.py --peticiones 3 --salida evidencias/I05a_datos_alterados.json
python scripts/datos.py restaurar --respaldo respaldos/ARCHIVO.json
python scripts/verificar_servicio.py --esperadas app1,app2 --salida evidencias/I05b_restaurado.json
```
I06: otra persona del equipo repite todo desde este README en su PC.

Registros: `docker compose logs --tail 50` (el proxy muestra `upstream=` y el estado de cada petición).
Al terminar: `docker compose down` (las carpetas `data/`, `respaldos/` y `evidencias/` se conservan).

## Límites (no es alta disponibilidad)
- Todo corre en un solo computador: si cae, cae el servicio, y los respaldos también viven ahí.
- El JSON compartido es un punto único de fallo: si se corrompe, responden 503 las dos instancias (I05).
- `restart: unless-stopped` relanza un proceso que muere, no uno *unhealthy*.
- La app no usa secretos; `.env` está en `.gitignore` como regla para el futuro.
