# CLAUDE.md — Nodo Ruta (reto 16, hackatón EstudIA)

## Qué es

Reto de **infraestructura, no de desarrollo**: tomar la app Python del reto (rutas `/`, `/health`, `/pedidos`; JSON con 6 pedidos sintéticos) y entregar un despliegue reproducible con 2 instancias detrás de un punto de acceso común, datos fuera del contenedor, respaldo y restauración verificables, salud, registros, identificación de la instancia, pruebas con evidencia medida y un diseño en nube.

Equipo de 6 personas en macOS, Windows y Linux. Repositorio: `Cualquiera-INC/proyecto_hackaton_cualquiera_inc`.

## Estado

- **Local: hecho y probado.** El stack oficial es `despliegue/` (app1, app2, proxy NGINX con la interfaz web y respaldo) y se opera con `scripts/desplegar.py`. Evidencias I01–I08 en `EVIDENCIAS.md`.
- **AWS (plan gratuito para cuentas nuevas): en preparación.** Diseño: EC2 ×2 en dos zonas + ALB + S3 con versiones (`docs/02-arquitectura.md`). Todavía no se ha creado ningún recurso.
- **Mejoras pendientes medidas:** quitar `http_503` de `proxy_next_upstream`, fijar `python:3.12-slim`, `server_tokens off` y endurecer los contenedores (`docs/03-decisiones.md`).
- **Staging (rama `staging`, D12):** el equipo reabrió D9. `despliegue/` suma PostgreSQL primario + réplica en caliente (`basedatos/`, alias de lectura `pg-lectura`) y el microservicio `servicios/pedidos/` (pedidos1/pedidos2, alias de red `pedidos`), que lee la base en segundo plano cada 1 s y responde desde memoria; las apps lo llaman por HTTP con `PEDIDOS_URL`. Nunca usar nombres de contenedor individuales entre servicios: en la red `internal` resolver un nombre inexistente tarda ~8 s (STG02/STG09). Contraseña en `despliegue/secretos/db_password.txt` (Docker secret, ignorada por git). Destino: un servidor en AWS. Pruebas STG01–STG14 en `EVIDENCIAS.md`; detalle en `docs/07-staging-microservicios-postgres.md`. En `master` sigue el stack JSON.

## Mapa

- `app.py`, `Dockerfile`, `pedidos.json`: app del reto con cambios mínimos y datos originales (no se modifican).
- `despliegue/`: `compose.yaml` y `nginx.conf` oficiales. No se levanta con `compose up` a mano: lo hace `desplegar.py`.
- `scripts/`: `desplegar.py`, `datos.py`, `verificar_servicio.py`, `monitorear.py`, `ejecutar_local.py`.
- `docs/`: 01 reto, 02 arquitectura, 03 decisiones, 04 seguridad y costos, 05 cómo funciona, 06 pitch.
- `evidencias/`: el prefijo del archivo es el ID de la prueba (`I05c_…`). `EVIDENCIAS.md` es la única bitácora.
- `frontend-nodo/`: interfaz web React + Vite de solo lectura. La construye `despliegue/Dockerfile.proxy` y el proxy la sirve en `/` (D11).
- `.github/workflows/`: `frontend.yml` (lint + build) y `contenedores.yml` (construye la referencia y hace la prueba de punta a punta de `despliegue/`).
- `ayuda_opcional/` y `recursos-reto/`: material original del reto, solo como referencia.

## Comandos

```text
python scripts/datos.py preparar        # staging: crea el secreto de la base (NODO_DB_PASSWORD o pregunta)
python scripts/datos.py respaldar | verificar | simular-error | restaurar --respaldo respaldos/<x>.dump
python scripts/desplegar.py desplegar --version v1
python scripts/desplegar.py rollback
python scripts/desplegar.py estado
python scripts/verificar_servicio.py --esperadas app1,app2 --salida evidencias/<ID>_<nombre>.json
python scripts/monitorear.py --segundos 120 --salida evidencias/<ID>_<nombre>.json
docker compose -f despliegue/compose.yaml ps | logs --tail 50 | down
```

## Reglas no negociables

1. Solo datos sintéticos. Nunca conectar con servicios reales.
2. **Cero costos.** En AWS: alerta de presupuesto antes de crear nada, etiqueta `proyecto=nodo-ruta` y destruir todo al terminar. No proponer recursos de pago.
3. Ningún secreto en la imagen ni en el repo. Revisar los cambios antes de cada commit.
4. Exposición mínima: solo el proxy o el ALB reciben tráfico; las apps no llevan `ports:`.
5. Pruebas destructivas solo sobre copias; el respaldo vive fuera de lo que se modifica.
6. Honestidad: nunca "alta disponibilidad" para contenedores en un mismo computador. Distinguir **probado** de **diseñado**.
7. Medir, no estimar: los tiempos salen de scripts con marcas de tiempo. Si una prueba falla, se reporta tal cual.
8. Cambios mínimos a `app.py`: solo lo necesario para observarla y desplegarla.

## Convenciones

- Español en documentación, commits y mensajes. Commits semánticos (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- Markdown con diagramas Mermaid.
- Scripts en Python con solo la biblioteca estándar, ejecutables directamente; rutas con `pathlib`.
- Imágenes con etiqueta de versión, nunca `latest`; imágenes base con versión fija.
- Finales de línea LF (`.gitattributes`).
- Trabajar en ramas y abrir PR; no hacer push directo a `main`.
- No ampliar el alcance (Kubernetes, multirregión, monitoreo pesado) sin que se pida: el reto premia un MVP medido y honesto.
