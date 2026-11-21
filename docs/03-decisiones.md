# 03 · Decisiones técnicas

Formato corto: qué decidimos, por qué y qué descartamos. 🟢 aceptada · 🟡 propuesta · 🔴 descartada.

## D1 · Orquestación local con Docker Compose 🟢
Lo trae la ayuda del reto, el equipo lo conoce y funciona igual en macOS, Windows y Linux. Descartado: Kubernetes (excesivo para 2 instancias).

## D2 · NGINX como proxy inverso 🟢
Punto de acceso común con reparto por turnos y reintento en la otra instancia. Su limitación (solo detección pasiva) está documentada y se resuelve en AWS con el health check del ALB. Descartados: Traefik y HAProxy (no aportan nada para este alcance).

## D3 · Datos: el JSON del reto, montado en solo lectura 🟢
La app lee `data/pedidos.json` en cada consulta. Se monta la **carpeta** `data/` (no el archivo) para poder reemplazarlo de forma atómica. Es lo más simple que cumple "datos fuera del contenedor" sin tocar la app.

## D4 · Respaldo con `datos.py` + servicio automático cada 5 min 🟢
Copia y huella SHA-256 que se verifica antes de restaurar, y nunca respalda un archivo dañado. RPO ≤ 5 min. En AWS, S3 con historial de versiones. Pendiente: rotar los respaldos antiguos.

## D5 · Despliegue escalonado con imágenes versionadas 🟢
`scripts/desplegar.py` actualiza una instancia a la vez, verifica salud, versión y enrutamiento, y revierte solo si la nueva falla. Imágenes `nodo-ruta:<versión>`, nunca `latest`. Responde a "una actualización introduce un error y las consultas dejan de responder" (I07, I08).

## D6 · Cambios mínimos a `app.py` 🟢
Solo para observar y desplegar: `version_app`, apagado ordenado con SIGTERM y el hostname cuando falta `INSTANCE_ID`. Además, CORS (`Access-Control-Allow-Origin: *` y `OPTIONS`) para que la interfaz web pueda consultar la API. Nada de lógica de negocio nueva.

## D7 · Scripts en Python con solo la biblioteca estándar 🟢
El equipo usa macOS, Windows y Linux. Cada script se ejecuta directamente (`python scripts/x.py`) y no hace falta instalar nada.

## D8 · Nube: AWS (plan gratuito) con EC2 + ALB + S3 🟢
El equipo tiene una cuenta nueva con el plan gratuito. Es la traducción directa del diseño local y permite probar la caída de una máquina. Detalle en [02-arquitectura.md](02-arquitectura.md).
- 🔴 ECS Fargate + RDS Multi-AZ: más caro y no hace falta para 6 pedidos de solo lectura.
- 🔴 Azure Container Apps: la cuenta disponible es de AWS.
- 🔴 EKS: cobra el panel de control y es excesivo.

## D9 · Microservicios y base de datos → fase 2 🔴 (por ahora)
Se habían propuesto en el encuentro 1 (3 microservicios + PostgreSQL). Se descartaron al llegar el paquete:
- partir una app de 3 rutas no le aporta nada al cliente;
- obligaría a reescribir la app, lo que rompe la regla de cambios mínimos;
- en local la base de datos sería otro punto único de falla;
- no cabe en el tiempo de construcción.

**Se reconsideran si** los pedidos pasan a modificarse a cada rato desde muchos puntos. Ahí sí hace falta una base de datos.

**Actualización (21-11): superada.** El equipo reabrió la decisión y la aceptó con evidencia medida; ver D12.

## D10 · Observabilidad sin herramientas pesadas 🟢
`instancia` y `version_app` en cada respuesta, el log de NGINX con el upstream y el tiempo, los healthchecks y los scripts `verificar_servicio.py` y `monitorear.py` como evidencia. En AWS: CloudWatch Logs y las métricas del ALB. Descartados: Prometheus y Grafana (fuera de alcance).

## D11 · Interfaz web de solo lectura en React + Vite 🟢 (PR #5, Silvia)
Una interfaz para que operaciones consulte los pedidos y el estado sin leer JSON. Es solo lectura y no cambia la API. Su CI está en GitHub Actions. Integrada al stack oficial: la imagen del proxy (`despliegue/Dockerfile.proxy`) la construye dentro de Docker y la sirve en `/`. Por eso el JSON de bienvenida de la app (`/`) ya no se ve a través del proxy; la API sigue en `/pedidos` y `/health`. En AWS se serviría desde S3 detrás de CloudFront.

## D12 · Microservicio de pedidos + PostgreSQL 🟢 (21-11, decisión del equipo)
Se reabre D9 y se acepta al integrar la rama `staging` a `main`, con 14 pruebas medidas (STG01–STG14). Motivo: pasar de datos fijos en un JSON a una base que pueda recibir cambios desde varios puntos, que es justo la condición que D9 dejó abierta.
- **Diseño mínimo:** un solo microservicio nuevo (`servicio-pedidos`, 2 réplicas) entre las apps y PostgreSQL. Las apps mantienen el contrato público (`/pedidos`, `/health`), así que la interfaz, los scripts de prueba y el despliegue escalonado siguen funcionando.
- **`app.py`:** con `PEDIDOS_URL` pide los datos por HTTP; sin ella, lee el JSON como antes. el modo JSON sigue funcionando.
- **Seguridad:** red de datos `internal` sin salida a internet; PostgreSQL sin puertos publicados; contraseña como Docker secret fuera del repositorio; conexión de solo lectura con `statement_timeout`.
- **Costo:** $0 en local. Dónde vive la base en AWS está abierto en D13. Detalle del diseño: [08-postgres-y-microservicio-pedidos.md](08-postgres-y-microservicio-pedidos.md).
- **Tolerancia a fallos de la base:** una réplica en caliente (streaming replication) y una copia en memoria en el microservicio, que lee la base en segundo plano. Medido: caída del primario y caída de las dos bases con 0 errores (STG08, STG12, STG14).
- **Lo que empeora y se reconoce:** hay más piezas que operar, las escrituras dependen del primario (sin promoción automática) y primario y réplica comparten máquina. Se tolera la caída de una *base*, no la de la *máquina*.

## D13 · Dónde vive PostgreSQL en AWS 🟡 (abierta)
El diseño de AWS ([02-arquitectura.md](02-arquitectura.md)) lleva los datos como JSON en S3, sincronizado a cada EC2. Con PostgreSQL eso ya no aplica y hay que decidir de nuevo. Opciones:

| Opción | Cómo queda | A favor | En contra |
|---|---|---|---|
| A. Una EC2 con todo el stack | El `compose.yaml` actual en una máquina | Lo más simple; es lo ya probado en local | No demuestra la caída de una máquina; sin ALB útil; una sola zona |
| **B. 2 EC2 (apps + pedidos) en dos zonas + RDS PostgreSQL** | Las EC2 sin estado; la base administrada | Conserva la prueba de apagar una máquina; sin operar la base | RDS consume créditos por hora; **verificar** en la consola qué instancias y si Multi-AZ permite el plan gratuito |
| C. 2 EC2 con primario en una y réplica en la otra | Replicación entre zonas, sin RDS | Sin servicio administrado | Se opera a mano y la promoción es manual; más riesgo |

**Propuesta:** B con una instancia RDS pequeña. En la caída de una EC2 se mide el comportamiento; la copia en memoria del microservicio cubre caídas cortas de la base. **No** se promete en AWS el "0 errores" medido en local (ahí la réplica se lee en vivo): en la nube es solo diseño hasta medirlo.

## D14 · Infraestructura en AWS con CloudFormation 🟢 (21-11)
La nube pasa de diseño a implementación. Las plantillas viven en `infra/aws/` y reemplazan la idea de scripts con AWS CLI: crear y **destruir** con una pila. GitHub Actions entra a AWS por OIDC, sin claves guardadas (probado: rol `github-actions-nodo-ruta`, solo la rama `main`, hoy sin permisos). Los permisos del rol se agregan solo cuando una plantilla los necesita, y mínimos.

## Pendientes medidos (mejoras para el siguiente PR)

| Mejora | Por qué | Estado |
|---|---|---|
| Quitar `http_503` del reintento de NGINX | Con datos dañados el usuario ve 502 y las instancias quedan castigadas hasta 3 s | 🟡 medido en laboratorio |
| Fijar `python:3.12-slim` en el Dockerfile | `python:3-slim` hoy instala 3.15 | 🟡 |
| `server_tokens off` | No mostrar la versión de NGINX | 🟡 |
| Endurecer contenedores (`read_only`, `cap_drop`, `no-new-privileges`) | Menos privilegios | 🟡 |
