# infra/aws - plantillas de CloudFormation

Todo va en **us-east-2 (Ohio)**: es la unica region que permite la politica de la organizacion (EC2, CloudFormation, RDS, ELB, ECS). Cada comando lleva `--region us-east-2`. Decisiones: D13 y D14 en `docs/03-decisiones.md`; diagrama en `docs/02-arquitectura.md`.

## Que crea cada plantilla

| Plantilla | Estado | Crea | Costo |
|---|---|---|---|
| `01-red.yaml` | escrita, validada con `ValidateTemplate`, **no desplegada** | VPC propia (`10.20.0.0/16`), 2 subredes publicas (ALB y EC2) y 2 privadas (RDS) en 2 zonas, Internet Gateway, tablas de rutas y los grupos de seguridad ALB -> EC2 (8080) -> RDS (5432) | **Gratis** (sin NAT Gateway ni IP elasticas) |
| `02-datos.yaml` | pendiente | RDS PostgreSQL Single-AZ en las subredes privadas, S3 de respaldos | por revisar |
| `03-computo.yaml` | pendiente | 2 EC2 (app + pedidos), ALB, target group con health check a `/health`, rol para SSM | por revisar |

Las EC2 van en subredes publicas con IP publica (para bajar imagenes y usar SSM sin NAT) pero su grupo de seguridad solo acepta el puerto 8080 desde el ALB y no tiene SSH. Las plantillas siguientes toman los valores con `Fn::ImportValue` de los exports `<nombre-de-la-pila>-VpcId`, `-SubredesPublicas`, `-SubredesPrivadas` (listas separadas por coma; usar `Fn::Split`), `-SgAlb`, `-SgEc2` y `-SgRds`.

## Orden de despliegue

1. `01-red.yaml` (nombre de pila sugerido: `nodo-ruta-red`)
2. `02-datos.yaml`
3. `03-computo.yaml`

Para destruir, en orden inverso (una pila no se puede borrar mientras otra importe sus exports).

## Comandos

Requieren credenciales activas. Cambia `TU_IP` por tu IP publica (por ejemplo la que muestra `curl https://checkip.amazonaws.com`).

```bash
# Validar (no crea nada)
aws cloudformation validate-template --region us-east-2 --template-body file://infra/aws/01-red.yaml

# Crear
aws cloudformation create-stack --region us-east-2 --stack-name nodo-ruta-red \
  --template-body file://infra/aws/01-red.yaml \
  --parameters ParameterKey=CidrAcceso,ParameterValue=TU_IP/32 \
  --tags Key=proyecto,Value=nodo-ruta
aws cloudformation wait stack-create-complete --region us-east-2 --stack-name nodo-ruta-red

# Ver salidas
aws cloudformation describe-stacks --region us-east-2 --stack-name nodo-ruta-red \
  --query "Stacks[0].Outputs" --output table

# Destruir
aws cloudformation delete-stack --region us-east-2 --stack-name nodo-ruta-red
aws cloudformation wait stack-delete-complete --region us-east-2 --stack-name nodo-ruta-red
```

Si cambia tu IP, actualiza la pila con `update-stack` y el nuevo `CidrAcceso`. `0.0.0.0/0` esta bloqueado por una regla de la plantilla.

## Nota de costo

La plantilla de red **no cuesta nada**: VPC, subredes, Internet Gateway, tablas de rutas y grupos de seguridad son gratis. El costo aparece con el ALB, las EC2 y RDS (plantillas 02 y 03): revisar los limites del plan gratuito antes de crearlas y destruir todo al terminar.
