# CLAUDE.md — Nodo Ruta (reto 16, hackatón EstudIA)

## Qué es

Reto de **infraestructura, no de desarrollo**: tomar la app Python del reto (rutas `/`, `/health`, `/pedidos`; JSON con 6 pedidos sintéticos) y entregar un despliegue reproducible con 2 instancias detrás de un punto de acceso común, datos fuera del contenedor, respaldo y restauración verificables, salud, registros, identificación de la instancia, pruebas con evidencia medida y un diseño en nube.

Equipo de 6 personas en macOS, Windows y Linux. Repositorio: `Cualquiera-INC/proyecto_hackaton_cualquiera_inc`.

## Estado

- **Local: hecho y probado, con PostgreSQL.** El stack oficial es `despliegue/` (proxy NGINX con la interfaz web, app1/app2, microservicio `pedidos1/pedidos2`, PostgreSQL primario + réplica en caliente y respaldo con `pg_dump`) y se opera con `scripts/desplegar.py`. Evidencias I01–I08 (stack con JSON) y STG01–STG14 (stack con PostgreSQL) en `EVIDENCIAS.md`. Diseño y límites en `docs/08-postgres-y-microservicio-pedidos.md`.
- **AWS (plan gratuito para cuentas nuevas): pasa a implementación con CloudFormation.** Ya existen en la cuenta, sin recursos de cómputo: la alerta de presupuesto, el proveedor OIDC de GitHub y el rol `github-actions-nodo-ruta` (sin permisos; solo acepta este repo en `main`; prueba en `.github/workflows/prueba-oidc-aws.yml`). Dónde vive PostgreSQL en AWS está abierto: D13 en `docs/03-decisiones.md`.
- **Plan por fases** (pulir local → preparar AWS → construir → probar y destruir → pitch): `docs/07-plan-y-fases.md`. Mantenerlo al día en cada PR.
- **PostgreSQL y el microservicio de pedidos están aceptados (D12; D9 quedó superado).** Nunca usar nombres de contenedor individuales entre servicios: en la red `internal` resolver un nombre inexistente tarda ~8 s (STG02/STG09); se usan los alias `pedidos` y `pg-lectura`. Contraseña en `despliegue/secretos/db_password.txt` (Docker secret, ignorada por git).
- **Mejoras pendientes medidas:** quitar `http_503` de `proxy_next_upstream`, fijar `python:3.12-slim`, `server_tokens off` y endurecer los contenedores (`docs/03-decisiones.md`).

## Mapa

- `app.py`, `Dockerfile`, `pedidos.json`: app del reto con cambios mínimos y datos originales (no se modifican).
- `servicios/pedidos/` y `basedatos/`: microservicio de pedidos (solo lectura) y esquema, datos iniciales y réplica de PostgreSQL.
- `despliegue/`: `compose.yaml` y `nginx.conf` oficiales. No se levanta con `compose up` a mano: lo hace `desplegar.py`.
- `scripts/`: `desplegar.py`, `datos.py`, `verificar_servicio.py`, `monitorear.py`, `ejecutar_local.py`.
- `docs/`: 01 reto, 02 arquitectura, 03 decisiones, 04 seguridad y costos, 05 cómo funciona, 06 pitch, 07 plan y fases, 08 PostgreSQL y microservicio de pedidos.
- `evidencias/`: el prefijo del archivo es el ID de la prueba (`I05c_…`). `EVIDENCIAS.md` es la única bitácora.
- `frontend-nodo/`: interfaz web React + Vite de solo lectura. La construye `despliegue/Dockerfile.proxy` y el proxy la sirve en `/` (D11).
- `.github/workflows/`: `frontend.yml` (lint + build) y `contenedores.yml` (construye la referencia y hace la prueba de punta a punta de `despliegue/`).
- `ayuda_opcional/` y `recursos-reto/`: material original del reto, solo como referencia.

## Comandos

```text
python scripts/datos.py preparar        # crea el secreto de la base (NODO_DB_PASSWORD o pregunta)
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
