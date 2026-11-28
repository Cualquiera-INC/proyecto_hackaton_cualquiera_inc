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

## D15 · Cómo corren los contenedores en las EC2 🟡 (23-11, plantilla escrita y validada, sin desplegar)
Sin ECR ni GHCR por ahora (la política de la organización solo menciona EC2, CloudFormation, RDS, ELB y ECS, y el repo es público). El user data de `infra/aws/03-computo.yaml` instala Docker y git, trae el repo en `VersionGit` (etiqueta o hash, sin valor por defecto) y ejecuta `despliegue/aws/iniciar.sh`, que: lee la clave de SSM, construye `nodo-ruta:<versión>` y `nodo-ruta-pedidos:<versión>`, carga la base **una sola vez** (`basedatos/aws/cargar-inicial.sql`: candado `pg_advisory_lock`, solo si no existe la tabla `pedidos`, en una transacción) y levanta los dos contenedores con `restart: unless-stopped`.
- **Sin Docker Compose:** AL2023 no trae el plugin y bajarlo sin verificar suma un riesgo; son dos `docker run` en una red propia.
- **Identificación:** `INSTANCE_ID` = zona + id de EC2 (IMDSv2). `app.py` no cambia (la instancia ya viaja en el cuerpo JSON; no hay encabezado `X-Instance-Id`).
- **Supuestos:** el repo sigue público y el commit está en GitHub; la app usa el usuario maestro de RDS (el servicio fuerza solo lectura por sesión); `rds.force_ssl` de RDS 17 funciona con `sslmode=prefer` (por probar); sin HTTPS (no hay dominio).
- **Se fijó** `python:3.12-slim` en el `Dockerfile` raíz (antes `python:3-slim`), pendiente ya listado abajo.
- **Respaldo:** `despliegue/aws/respaldar.sh` (manual por SSM) hace `pg_dump` y lo sube a `s3://<bucket>/respaldos/`. Restaurar queda pendiente.

## D16 · La interfaz en AWS: S3 + CloudFront 🟡 (23-11, elegida por el usuario; plantilla escrita y validada, sin desplegar)
Hay que decidir cómo se sirve `frontend-nodo/` en AWS (D11). La interfaz es de una sola vista, usa rutas relativas (`/pedidos`, `/health`) y se construye con `npm ci && npm run build`. Opciones:

| Opción | Cómo queda | A favor | En contra |
|---|---|---|---|
| A. NGINX en las EC2 | La imagen `nodo-ruta-proxy` en cada EC2 detrás del ALB | Reutiliza lo ya probado en local | Sin HTTPS (no hay dominio); sube el tiempo de arranque y mezcla interfaz y API en las EC2 |
| **B. S3 + CloudFront** 🟢 | Bucket privado con la interfaz; CloudFront envía `/pedidos` y `/health` al ALB | HTTPS en `*.cloudfront.net` sin comprar dominio; las EC2 no cambian; dentro del plan gratuito de CloudFront | Suma dos servicios; la SCP de la organización no se pudo probar contra la creación de CloudFront (solo se sabe que deja leer) |

**Elegida: B** (decisión del usuario). Implementación: `infra/aws/04-front.yaml` (pila `nodo-ruta-front`), más cambios en `01-red.yaml` y `03-computo.yaml`.
- **Bucket privado** (bloqueo público, SSE-S3, solo HTTPS) que solo lee CloudFront por OAC con `AWS:SourceArn` de la distribución. Comportamientos exactos `/pedidos` y `/health` al ALB, sin caché y solo GET/HEAD; sin página de error global (no se enmascaran errores de la API).
- **Consecuencias que se reconocen:** HTTPS **solo hasta CloudFront**; de CloudFront al ALB el tráfico va en **HTTP** (el ALB no tiene certificado). El ALB queda abierto a la prefix list de CloudFront (el grupo de seguridad no distingue a cuál distribución); se mitiga con **dos capas**: el listener responde 403 salvo que llegue el encabezado secreto `X-Origin-Verify` (o la IP sea `CidrAcceso`), y una **CloudFront Function** devuelve 403 a IP fuera de `CidrAcceso`. La clave es visible para quien pueda leer las reglas del ALB y viaja en HTTP entre CloudFront y el ALB: es una mitigación, no un control fuerte.
- **Límites:** la prefix list pesa 55 de las 60 reglas del grupo del ALB; solo IPv4 y puerto 80. Las actualizaciones de red y cómputo son in situ (sin reemplazar ALB, target group ni EC2); el riesgo de reemplazo está en las AMI de SSM, por eso se usa `UsePreviousValue`.
- **Probado vs. diseñado:** ver AWS08 en `infra/aws/PRUEBAS.md`. Hasta ejecutarla todo esto es solo diseño validado con `ValidateTemplate`.

## D17 · Despliegue automatizado con un script: `scripts/aws_nodo.py` y GitHub Actions 🟢 (24-11; script aceptado; Actions aceptado y política versionada, **sin aplicar ni ejecutar**)
Desplegar en AWS eran ~10 bloques de comandos pegados a mano (contraseña en SSM, cuatro pilas en orden, clave de origen, `UsePreviousValue`, publicar el front, esperar al target group, probar, destruir vaciando buckets). Opciones:

| Opción | A favor | En contra |
|---|---|---|
| Seguir con los bloques de README y PRUEBAS | Nada nuevo que mantener | Fácil equivocarse (orden, parámetros, secretos en la terminal); no reproducible |
| **Script en Python (biblioteca estándar) que llama al AWS CLI** 🟡 | Un comando, igual en macOS, Windows y Linux, sin dependencias; mismo estilo que `desplegar.py` | Un script más que mantener; no sustituye a CloudFormation, lo orquesta |
| **GitHub Actions con OIDC que ejecuta el script** 🟢 | Despliegue desde el repo, sin claves en equipos, con bitácora como artifact | Exige dar permisos de despliegue al rol `github-actions-nodo-ruta` (hoy sin permisos); solo corre desde `main` |

**Se implementó la segunda** (`desplegar`, `estado`, `probar`, `destruir` y `--simular`; uso en `infra/aws/README.md`). Decisiones de diseño:
- **Idempotencia y seguridad de las actualizaciones:** las pilas existentes se actualizan con un change set que se revisa antes de ejecutar; si algo se reemplazaría (típico: AMI de SSM re-resuelta o un nuevo `VersionGit`) se aborta. Es el mismo control que se hacía a mano para D16.
- **Secretos:** `secrets.token_hex`, solo si faltan en SSM, y por archivos temporales 0600. La clave de origen queda en SSM (`/nodo-ruta/front/clave-origen`) para poder repetir el despliegue.
- **Supuestos:** el commit a desplegar debe estar en GitHub (las EC2 lo clonan); la API de etiquetas (`tag:GetResources`) está bloqueada por la SCP en us-east-1, por eso la verificación de CloudFront usa `list-distributions`.
- **Probado vs. diseñado:** la lógica de pilas, change sets y vaciado de buckets se probó contra respuestas simuladas, y `estado` y `--simular` contra la cuenta real (solo lecturas). **Falta** una ejecución real de `desplegar`, `probar` y `destruir` (se hace en la próxima prueba en AWS); hasta entonces es solo diseño con pruebas parciales.
- **Actions (aceptado):** `.github/workflows/aws.yml` (`workflow_dispatch` con `accion`, `cidr`, `version`, `confirmacion`) asume el rol por OIDC y llama al script. Solo corre desde `main` (el rol confía solo en esa rama), una ejecución a la vez, sin cancelar la que está en curso. En Actions la prueba de humo va por SSM en las EC2, porque el runner no es la IP de `CidrAcceso`.
- **Política del rol, versionada y sin aplicar:** `infra/aws/iam/politica-github-actions.json` (bloques explicados en su README). Mínimo privilegio razonable: CloudFormation solo `nodo-ruta-*`, IAM solo roles y perfiles `nodo-ruta-computo-*` con `PassRole` solo a EC2, SSM `/nodo-ruta/*`, `SendCommand` solo a instancias con `proyecto=nodo-ruta`, región us-east-2; sin `*:*` ni `iam:*`. Pasó `ValidatePolicy` sin hallazgos, pero **no se ha ejecutado nunca**: pueden faltar permisos en la primera corrida.
- **Riesgos que se reconocen:** quien lance el workflow puede crear recursos de pago (se mitiga con `main` solamente y la alerta de presupuesto); la sesión OIDC dura como máximo 1 h (`MaxSessionDuration`), justa para un despliegue de ~45 min; el repo es público, así que la IP de `cidr` queda visible en registros y artifact.

## D18 · Acceso público solo por CloudFront para el pitch: `AccesoPublico` / `--publico` 🟡 (28-11; plantilla y script escritos, **sin desplegar ni probar en AWS**)
El jurado y el público del pitch entran desde redes que no conocemos, y hasta ahora todo estaba cerrado a una sola IP (`CidrAcceso`). Opciones:

| Opción | A favor | En contra |
|---|---|---|
| Seguir con una sola IP | Superficie mínima | La demo solo funciona desde el computador del equipo; el jurado no puede abrirla |
| Abrir también el ALB a `0.0.0.0/0` | Sencillo | Expone el balanceador directo y quita el control de `X-Origin-Verify`; **descartada**: los candados de `01-red.yaml` y `03-computo.yaml` siguen prohibiendo `0.0.0.0/0` |
| **Abrir solo CloudFront** (`AccesoPublico=si`) 🟡 | El ALB sigue admitiendo solo la prefix list de CloudFront y la IP del equipo, con 403 por defecto y regla por `X-Origin-Verify`; un solo cambio, reversible | Cualquiera puede ver la interfaz y la API |

**Se eligió la tercera.** Diseño:
- Parámetro `AccesoPublico` (`si`/`no`, por defecto `no`) en `04-front.yaml`. Con `si`, la distribución deja de asociar la CloudFront Function de IP (`!If` con `AWS::NoValue`); la función sigue existiendo sin asociar. `CidrAcceso` sigue siendo la IP /32 del equipo (entra directo al ALB). No cambia el ALB ni sus candados.
- Cambiar el parámetro en una pila existente solo modifica `FunctionAssociations` (actualización sin interrupción): no reemplaza la distribución ni el bucket. El script lo comprueba con su change set (aborta si algo se reemplazaría).
- `aws_nodo.py desplegar --publico` (o la entrada `publico=si` de Actions) abre; un despliegue sin el flag vuelve a cerrar. `estado` muestra si CloudFront es público o restringido. La prueba de humo en modo público espera 200 desde el propio runner.
- **Riesgos:** cualquiera con la URL ve datos sintéticos de solo lectura; el tráfico y el costo de CloudFront quedan acotados por `PriceClass_100` y el nivel gratuito (1 TB y 10 millones de solicitudes al mes, ver `docs/04-seguridad-y-costos.md`), pero un abuso (miles de solicitudes) podría consumirlos; la URL `*.cloudfront.net` es difícil de adivinar, no secreta.
- **Mitigaciones:** el ALB sigue cerrado; la API es de solo lectura; el bucket es privado; se destruye todo el mismo día (`destruir`) y la alerta de presupuesto sigue activa.
- **Solo diseñado, no implementado:** AWS WAF con límite de tasa (es de pago, contra la regla de cero costos). Honestidad: esto es una apertura deliberada para la demo, no una configuración de producción.
- **Estado:** nada de esto se ha desplegado todavía. La plantilla no pudo validarse con `cfn-lint` (no instalado) ni con `validate-template` (sesión de AWS vencida); falta validar y probar el cambio en AWS.

## Pendientes medidos (mejoras para el siguiente PR)

| Mejora | Por qué | Estado |
|---|---|---|
| Quitar `http_503` del reintento de NGINX | Con datos dañados el usuario ve 502 y las instancias quedan castigadas hasta 3 s | 🟡 medido en laboratorio |
| Fijar `python:3.12-slim` en el Dockerfile | `python:3-slim` hoy instala 3.15 | 🟡 |
| `server_tokens off` | No mostrar la versión de NGINX | 🟡 |
| Endurecer contenedores (`read_only`, `cap_drop`, `no-new-privileges`) | Menos privilegios | 🟡 |
