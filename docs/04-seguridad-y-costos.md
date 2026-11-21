# 04 · Seguridad y costos

## Controles de seguridad

| Control | Cómo | Estado |
|---|---|---|
| Sin secretos en la imagen | Configuración por variables de entorno; `.dockerignore` excluye datos, respaldos y `.git` | ✅ |
| Sin secretos en el repositorio | `.env` y `despliegue/.env` en `.gitignore`; revisar los cambios antes de cada commit | ✅ |
| Exposición de red mínima | Solo el proxy publica puerto (`127.0.0.1:8080`); las apps no tienen `ports:` | ✅ |
| Contenedor sin root | `USER 10001` en el Dockerfile | ✅ |
| Datos en solo lectura dentro del contenedor | Montaje `read_only: true` | ✅ |
| Integridad de respaldos | SHA-256 verificado antes de restaurar | ✅ |
| Contraseña de la base como Docker secret | `POSTGRES_PASSWORD_FILE`; el archivo vive en `despliegue/secretos/` y git lo ignora | ✅ |
| Red de datos aislada | Red `internal` sin salida a internet; PostgreSQL sin `ports:` | ✅ |
| Microservicio de pedidos de solo lectura | Conexión de solo lectura y consultas cortadas a los 2 s | ✅ |
| Detección de corrupción en disco | `--data-checksums` (solo en bases nuevas) | ✅ |
| Roles separados de lectura y replicación | Hoy un solo usuario dueño de la base | 🟡 pendiente |
| Imágenes con versión | `nodo-ruta:<versión>` y `nginx:1.28-alpine` | ✅ |
| Imagen base fijada | `python:3.12-slim` | 🟡 pendiente (hoy `python:3-slim`) |
| Endurecimiento extra | `read_only`, `cap_drop: [ALL]`, `no-new-privileges` | 🟡 pendiente |
| **AWS:** firewall restrictivo | Las EC2 aceptan `:8080` solo desde el security group del ALB; sin puerto 22 | ⏳ diseño |
| **AWS:** mínimo privilegio | Rol de la EC2 con solo `s3:GetObject` en `actual/*` y escritura de logs | ⏳ diseño |
| **AWS:** sin claves guardadas | Rol de instancia (credenciales temporales) y Session Manager para administrar | ⏳ diseño |
| **AWS:** GitHub Actions sin claves | OIDC + rol `github-actions-nodo-ruta` que solo acepta este repo en `main` (identidad inmutable por ID) | ✅ conexión probada; permisos por definir según cada plantilla |
| **AWS:** contraseña de la base | Secrets Manager o SSM Parameter Store; nunca en la plantilla de CloudFormation ni en el repo | ⏳ diseño |

## Factores de costo en AWS (sin cifras)

Los precios cambian y la guía pide no inventarlos. En el plan gratuito para cuentas nuevas, el consumo **descuenta créditos**; la cuenta no cobra mientras no se cambie a un plan pago. Hay que confirmar las condiciones en la consola al crear la cuenta.

| Componente | Qué consume | Cómo lo controlamos |
|---|---|---|
| 2 EC2 | Horas encendidas × tamaño | Tipo elegible del plan gratuito; encender solo para probar |
| ALB | Horas activo + capacidad procesada | Suele ser lo más caro: crearlo para la prueba y borrarlo al terminar |
| IP públicas | Horas por cada IPv4 pública | Las mínimas posibles |
| S3 | GB guardados + solicitudes + versiones antiguas | Datos de KB; regla de expiración de versiones; intervalo de sincronización razonable |
| Discos EBS | GB-mes | Disco mínimo; se borran con la instancia |
| CloudWatch Logs | GB ingeridos + días de retención | Retención de 1 a 7 días |
| Transferencia de salida | GB hacia internet | Insignificante en la demo |
| Registro de imágenes | GB guardados (ECR) | GHCR público: sin costo |
| Base de datos (D13) | Si es RDS: horas de instancia y GB; si es EC2: disco EBS y memoria extra | Instancia pequeña, sin Multi-AZ salvo que se justifique y se verifique que el plan lo permite |
| CloudFront + S3 de la interfaz (opcional) | Solicitudes HTTPS, transferencia y GB del sitio estático | Solo si se despliega la interfaz; build de pocos KB |

## Antes de crear cualquier recurso

1. **Alerta de presupuesto** configurada (AWS Budgets) con aviso al correo del responsable.
2. Revisar los créditos disponibles y la fecha de vencimiento del plan.
3. Etiquetar todo con `proyecto=nodo-ruta` para poder encontrarlo y borrarlo.

## Destrucción al terminar (obligatoria)

0. **Si se creó con CloudFormation:** eliminar la pila borra casi todo. Después revisar lo que una pila no borra: buckets con objetos o versiones, snapshots manuales y log groups creados fuera de la plantilla.
1. Distribución de CloudFront, si se creó: deshabilitar y eliminar.
2. ALB y target group.
3. Las 2 EC2 (terminar, no solo detener; así se liberan el disco y la IP).
4. Buckets S3 (datos y, si existe, el de la interfaz) vaciados, **incluidas las versiones antiguas**, y luego eliminados.
5. Log group de CloudWatch.
5b. La base de datos (RDS, si se usó) y sus snapshots manuales.
6. Rol de IAM, security groups y alerta de presupuesto (esta al final). El proveedor OIDC y el rol de GitHub Actions se conservan si se va a volver a desplegar.
7. Revisar el panel de facturación y comprobar que no queda nada con la etiqueta `proyecto=nodo-ruta`.
