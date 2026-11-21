# CLAUDE.md — Nodo Ruta (reto 16, hackatón EstudIA)

## Qué es

Reto de **infraestructura, no de desarrollo**: tomar la app Python del reto (rutas `/`, `/health`, `/pedidos`; JSON con 6 pedidos sintéticos) y entregar un despliegue reproducible con 2 instancias detrás de un punto de acceso común, datos fuera del contenedor, respaldo y restauración verificables, salud, registros, identificación de la instancia, pruebas con evidencia medida y un diseño en nube.

Equipo de 6 personas en macOS, Windows y Linux. Repositorio: `Cualquiera-INC/proyecto_hackaton_cualquiera_inc`.

## Estado

- **Local: hecho y probado.** El stack oficial es `despliegue/` (app1, app2, proxy NGINX y respaldo) y se opera con `scripts/desplegar.py`. Evidencias I01–I08 en `EVIDENCIAS.md`.
- **AWS (plan gratuito para cuentas nuevas): en preparación.** Diseño: EC2 ×2 en dos zonas + ALB + S3 con versiones (`docs/02-arquitectura.md`). Todavía no se ha creado ningún recurso.
- **Mejoras pendientes medidas:** quitar `http_503` de `proxy_next_upstream`, fijar `python:3.12-slim`, `server_tokens off` y endurecer los contenedores (`docs/03-decisiones.md`).
- Descartado por ahora (D9): microservicios y PostgreSQL. No proponerlos de nuevo sin un motivo nuevo.

## Mapa

- `app.py`, `Dockerfile`, `pedidos.json`: app del reto con cambios mínimos y datos originales (no se modifican).
- `despliegue/`: `compose.yaml` y `nginx.conf` oficiales. No se levanta con `compose up` a mano: lo hace `desplegar.py`.
- `scripts/`: `desplegar.py`, `datos.py`, `verificar_servicio.py`, `monitorear.py`, `ejecutar_local.py`.
- `docs/`: 01 reto, 02 arquitectura, 03 decisiones, 04 seguridad y costos, 05 cómo funciona, 06 pitch.
- `evidencias/`: el prefijo del archivo es el ID de la prueba (`I05c_…`). `EVIDENCIAS.md` es la única bitácora.
- `ayuda_opcional/` y `recursos-reto/`: material original del reto, solo como referencia.

## Comandos

```text
python scripts/datos.py preparar
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
