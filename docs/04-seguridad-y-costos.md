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
| Imágenes con versión | `nodo-ruta:<versión>` y `nginx:1.28-alpine` | ✅ |
| Imagen base fijada | `python:3.12-slim` | 🟡 pendiente (hoy `python:3-slim`) |
| Endurecimiento extra | `read_only`, `cap_drop: [ALL]`, `no-new-privileges` | 🟡 pendiente |
| **AWS:** firewall restrictivo | Las EC2 aceptan `:8080` solo desde el security group del ALB; sin puerto 22 | ⏳ diseño |
| **AWS:** mínimo privilegio | Rol de la EC2 con solo `s3:GetObject` en `actual/*` y escritura de logs | ⏳ diseño |
| **AWS:** sin claves guardadas | Rol de instancia (credenciales temporales) y Session Manager para administrar | ⏳ diseño |

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

## Antes de crear cualquier recurso

1. **Alerta de presupuesto** configurada (AWS Budgets) con aviso al correo del responsable.
2. Revisar los créditos disponibles y la fecha de vencimiento del plan.
3. Etiquetar todo con `proyecto=nodo-ruta` para poder encontrarlo y borrarlo.

## Destrucción al terminar (obligatoria)

1. ALB y target group.
2. Las 2 EC2 (terminar, no solo detener; así se liberan el disco y la IP).
3. Bucket S3 vaciado, **incluidas las versiones antiguas**, y luego eliminado.
4. Log group de CloudWatch.
5. Rol de IAM, security groups y alerta de presupuesto (esta al final).
6. Revisar el panel de facturación y comprobar que no queda nada con la etiqueta `proyecto=nodo-ruta`.
