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
- **Costo:** $0 en local. En AWS: RDS (D13). Detalle del diseño: [08-postgres-y-microservicio-pedidos.md](08-postgres-y-microservicio-pedidos.md).
- **Tolerancia a fallos de la base:** una réplica en caliente (streaming replication) y una copia en memoria en el microservicio, que lee la base en segundo plano. Medido: caída del primario y caída de las dos bases con 0 errores (STG08, STG12, STG14).
- **Lo que empeora y se reconoce:** hay más piezas que operar, las escrituras dependen del primario (sin promoción automática) y primario y réplica comparten máquina. Se tolera la caída de una *base*, no la de la *máquina*.

## D13 · PostgreSQL en AWS: 2 EC2 + RDS 🟢 (21-11, elegida entre tres opciones)
El diseño de AWS ([02-arquitectura.md](02-arquitectura.md)) llevaba los datos como JSON en S3. Con PostgreSQL había que decidir de nuevo. Se evaluaron:

| Opción | Cómo queda | A favor | En contra |
|---|---|---|---|
| A. Una EC2 con todo el stack | El `compose.yaml` actual en una máquina | Lo más simple; ya probado en local | No demuestra la caída de una máquina; una sola zona |
| **B. 2 EC2 (app + pedidos) en dos zonas + RDS PostgreSQL** 🟢 | Las EC2 sin estado; la base administrada | Conserva la prueba de apagar una máquina; no se opera la base | RDS consume créditos por hora |
| C. Primario y réplica en EC2 distintas | Replicación entre zonas, sin RDS | Sin servicio administrado | Se opera a mano; promoción manual; más riesgo |

**Elegida: B.** Se verificó en la documentación de AWS qué permite el plan gratuito para RDS: PostgreSQL en `db.t3.micro` o `db.t4g.micro`, **solo Single-AZ** (no Multi-AZ).

Consecuencias que se reconocen:
- **La base en AWS es un punto único de falla** (una instancia, una zona). No hay réplica en caliente como en local. Multi-AZ exigiría un plan de pago, y se deja como diseño.
- Lo que sí tolera: la caída de **una EC2** (la otra sigue, detrás del ALB) y caídas **cortas** de la base (la copia en memoria del microservicio sirve la última lectura buena hasta 5 min).
- **No se promete** en AWS el "0 errores" medido en local para la caída del primario: allá la réplica se lee en vivo y aquí no existe. Se mide y se reporta lo que salga.
- Respaldos: los automáticos de RDS (retención corta) y `pg_dump` hacia S3 con versiones. Se confirma al implementar.
- Los servicios `postgres`, `postgres-replica` y `respaldo` del `compose.yaml` no corren en AWS; `pedidos` apunta al endpoint de RDS.
- Implementación (`infra/aws/02-datos.yaml`, validada, sin desplegar): PostgreSQL 17 (misma versión mayor que local), `db.t4g.micro` por defecto con `db.t3.micro` como parámetro (ambas aparecen disponibles en us-east-2), 20 GB gp2 cifrada, contraseña en SSM SecureString, 1 día de respaldos automáticos (supuesto) y borrado sin snapshot final. El SG de RDS (de `01-red.yaml`) acepta solo a las EC2.

## D14 · Infraestructura en AWS con CloudFormation 🟢 (21-11)
La nube pasa de diseño a implementación. Las plantillas viven en `infra/aws/` y reemplazan la idea de scripts con AWS CLI: crear y **destruir** con una pila. GitHub Actions entra a AWS por OIDC, sin claves guardadas (probado: rol `github-actions-nodo-ruta`, solo la rama `main`, hoy sin permisos). Los permisos del rol se agregan solo cuando una plantilla los necesita, y mínimos.

## Pendientes medidos (mejoras para el siguiente PR)

| Mejora | Por qué | Estado |
|---|---|---|
| Quitar `http_503` del reintento de NGINX | Con datos dañados el usuario ve 502 y las instancias quedan castigadas hasta 3 s | 🟡 medido en laboratorio |
| Fijar `python:3.12-slim` en el Dockerfile | `python:3-slim` hoy instala 3.15 | 🟡 |
| `server_tokens off` | No mostrar la versión de NGINX | 🟡 |
| Endurecer contenedores (`read_only`, `cap_drop`, `no-new-privileges`) | Menos privilegios | 🟡 |
