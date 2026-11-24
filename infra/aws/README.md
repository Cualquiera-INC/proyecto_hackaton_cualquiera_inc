# infra/aws - plantillas de CloudFormation

Todo va en **us-east-2 (Ohio)**: es la unica region que permite la politica de la organizacion (EC2, CloudFormation, RDS, ELB, ECS). Cada comando lleva `--region us-east-2`. Decisiones: D13 y D14 en `docs/03-decisiones.md`; diagrama en `docs/02-arquitectura.md`.

## Que crea cada plantilla

| Plantilla | Estado | Crea | Costo |
|---|---|---|---|
| `01-red.yaml` | **desplegada** como `nodo-ruta-red` (23-11, evidencia AWS01) | VPC propia (`10.20.0.0/16`), 2 subredes publicas (ALB y EC2) y 2 privadas (RDS) en 2 zonas, Internet Gateway, tablas de rutas y los grupos de seguridad ALB -> EC2 (8080) -> RDS (5432) | **Gratis** (sin NAT Gateway ni IP elasticas) |
| `02-datos.yaml` | **desplegada** como `nodo-ruta-datos` (23-11, evidencia AWS02) | RDS PostgreSQL 17 Single-AZ (`db.t4g.micro`, 20 GB gp2, cifrada, sin acceso publico) en las subredes privadas y bucket S3 de respaldos (versiones, cifrado, expiracion a 7 dias) | **RDS y S3 consumen creditos** (ver nota de costo) |
| `03-computo.yaml` | validada, **sin desplegar** | 2 EC2 (app + pedidos en contenedores), ALB HTTP, target group con health check a `/health`, rol IAM de minimo privilegio con SSM | **EC2, ALB e IPv4 publicas consumen creditos** (ver nota de costo) |

Las EC2 van en subredes publicas con IP publica (para bajar imagenes y usar SSM sin NAT) pero su grupo de seguridad solo acepta el puerto 8080 desde el ALB y no tiene SSH. Las plantillas siguientes toman los valores con `Fn::ImportValue` de los exports `<nombre-de-la-pila>-VpcId`, `-SubredesPublicas`, `-SubredesPrivadas` (listas separadas por coma; usar `Fn::Split`), `-SgAlb`, `-SgEc2` y `-SgRds`.

## Orden de despliegue

1. `01-red.yaml` (nombre de pila sugerido: `nodo-ruta-red`)
2. `02-datos.yaml`
3. `03-computo.yaml`

Para destruir, en orden inverso (una pila no se puede borrar mientras otra importe sus exports).

## Comandos de la pila de red

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

## Pila de datos (`02-datos.yaml`, pila `nodo-ruta-datos`)

Requiere `nodo-ruta-red` creada. **Antes de crearla, el usuario crea la contrasena** como parametro SecureString de SSM (nivel estandar, gratis). La plantilla solo conoce la ruta, nunca el valor. Con `read -s` la clave no queda en el historial ni se imprime:

```bash
read -s -p "Contrasena de la base: " DBPASS; echo
aws ssm put-parameter --region us-east-2 --name /nodo-ruta/db/password \
  --type SecureString --tier Standard --value "$DBPASS" \
  --tags Key=proyecto,Value=nodo-ruta
unset DBPASS
```

Usa una clave de 12 a 30 caracteres sin `/`, `@`, comillas ni espacios (RDS los rechaza). Para cambiarla mas tarde: el mismo comando con `--overwrite` (y sin `--tags`), y luego actualizar la pila.

```bash
# Validar (no crea nada)
aws cloudformation validate-template --region us-east-2 --template-body file://infra/aws/02-datos.yaml

# Crear (RDS tarda ~10 a 15 minutos)
aws cloudformation create-stack --region us-east-2 --stack-name nodo-ruta-datos \
  --template-body file://infra/aws/02-datos.yaml \
  --tags Key=proyecto,Value=nodo-ruta
aws cloudformation wait stack-create-complete --region us-east-2 --stack-name nodo-ruta-datos

# Ver salidas (endpoint, puerto, base, bucket)
aws cloudformation describe-stacks --region us-east-2 --stack-name nodo-ruta-datos \
  --query "Stacks[0].Outputs" --output table
```

Si la politica de la organizacion bloquea S3 (no se pudo comprobar sin crear nada), la pila falla y revierte: crearla otra vez con `--parameters ParameterKey=CrearBucket,ParameterValue=false` (queda sin bucket) y borrar la pila fallida antes. Si la clase `db.t4g.micro` no se deja crear, probar `ParameterKey=ClaseInstancia,ParameterValue=db.t3.micro`.

### Destruir la pila de datos

Un bucket con objetos o versiones **no se borra** con la pila (falla con `BucketNotEmpty`). Vaciarlo primero, incluidas las versiones:

```bash
B=nodo-ruta-respaldos-$(aws sts get-caller-identity --query Account --output text)-us-east-2
aws s3 rm s3://$B --recursive --region us-east-2
# versiones y marcas de borrado (repetir si hay mas de 1000)
aws s3api delete-objects --region us-east-2 --bucket $B --delete "$(aws s3api list-object-versions --region us-east-2 --bucket $B --output json --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}')"
aws s3api delete-objects --region us-east-2 --bucket $B --delete "$(aws s3api list-object-versions --region us-east-2 --bucket $B --output json --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}')"

aws cloudformation delete-stack --region us-east-2 --stack-name nodo-ruta-datos
aws cloudformation wait stack-delete-complete --region us-east-2 --stack-name nodo-ruta-datos

# El parametro de SSM no pertenece a la pila: borrarlo al terminar todo
aws ssm delete-parameter --region us-east-2 --name /nodo-ruta/db/password
```

(Si un `delete-objects` dice que `Objects` es nulo, ya no quedaba nada de ese tipo.) RDS se borra **sin snapshot final** (`DeletionPolicy: Delete`) para que nada siga cobrando; los datos son sinteticos.

**Orden de destruccion: 03 -> 02 -> 01.** Una pila no se borra mientras otra importe sus exports.

## Nota de costo

- **Red (01):** gratis (VPC, subredes, Internet Gateway, tablas de rutas, grupos de seguridad).
- **RDS (02):** el plan gratuito de RDS cubre PostgreSQL en `db.t3.micro` o `db.t4g.micro` **solo Single-AZ**; no cubre Multi-AZ ni snapshots migrados ([documentacion de RDS, "AWS Free Tier on Amazon RDS"](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Welcome.html)). En cuentas creadas despues del 15-07-2025 el uso **descuenta de los creditos** (USD 100 al registrarse, hasta USD 100 mas por activar servicios, validos hasta 12 meses; [precios de RDS](https://aws.amazon.com/rds/pricing/)); no es "750 horas gratis" como en el esquema anterior. Mientras la instancia exista consume horas y almacenamiento.
- **Respaldos automaticos de RDS:** la plantilla usa 1 dia de retencion; AWS indica que con 1 dia lo normal es no pagar almacenamiento de respaldo ([blog de AWS Database](https://aws.amazon.com/blogs/database/demystifying-amazon-rds-backup-storage-costs/)). **Supuesto:** no verificamos si el plan gratuito impone un maximo de retencion; si `create-stack` lo rechaza, el error lo dira.
- **S3:** centavos con datos de KB; las reglas de ciclo de vida borran objetos a los 7 dias y versiones viejas a los 3.
- **SSM Parameter Store:** el nivel estandar es gratis. Se evita `ManageMasterUserPassword` porque guarda el secreto en Secrets Manager, que cobra por secreto.
- **ALB y EC2 (03):** consumen creditos por hora mientras existan. Referencias de lista (verificar, pueden variar): ALB ~USD 0.0225/h mas LCU ([precios de ELB](https://aws.amazon.com/elasticloadbalancing/pricing/)); cada IPv4 publica USD 0.005/h, 2 EC2 + 2 IPs del ALB ([precios de VPC](https://aws.amazon.com/vpc/pricing/)); t3.micro/t4g.micro elegibles del plan gratuito (verificado con `describe-instance-types`) pero tambien descuentan creditos ([precios de EC2](https://aws.amazon.com/ec2/pricing/on-demand/)). Orden de magnitud: unos USD 2 a 3 al dia con todo encendido. Crear para probar y destruir al terminar. Los discos gp3 de 8 GB tambien cobran hasta terminarse las instancias.


## Pila de computo (`03-computo.yaml`, pila `nodo-ruta-computo`)

Requiere `nodo-ruta-red` y `nodo-ruta-datos`. Las EC2 traen el codigo de GitHub (repo **publico**): antes de crear la pila hay que **subir a GitHub** la rama o etiqueta con `despliegue/aws/` y pasar su **hash de commit** (o etiqueta) en `VersionGit`. Diseno en D15 (`docs/03-decisiones.md`).

```bash
# Validar (no crea nada)
aws cloudformation validate-template --region us-east-2 --template-body file://infra/aws/03-computo.yaml

# Crear (CAPABILITY_IAM porque crea un rol; los nombres no son fijos). Tarda unos minutos
aws cloudformation create-stack --region us-east-2 --stack-name nodo-ruta-computo \
  --template-body file://infra/aws/03-computo.yaml \
  --parameters ParameterKey=VersionGit,ParameterValue=HASH_DEL_COMMIT \
  --capabilities CAPABILITY_IAM --tags Key=proyecto,Value=nodo-ruta
aws cloudformation wait stack-create-complete --region us-east-2 --stack-name nodo-ruta-computo

# Salidas (URL del ALB, ids de las EC2, ARN del target group)
aws cloudformation describe-stacks --region us-east-2 --stack-name nodo-ruta-computo \
  --query "Stacks[0].Outputs" --output table
```

Las EC2 tardan unos 3 a 6 minutos mas en construir las imagenes; hasta entonces el ALB las marca no saludables (503). Ver el estado y probar:

```bash
aws elbv2 describe-target-health --region us-east-2 --target-group-arn ARN_DEL_GRUPO
curl -s http://DNS_DEL_ALB/health          # repetir: "instancia" alterna entre las dos zonas
curl -s http://DNS_DEL_ALB/pedidos
```

Solo responde a `CidrAcceso` (la IP de la pila de red). Si el ALB no contesta, revisar que tu IP no haya cambiado.

**Entrar a una EC2 (sin SSH, por SSM Session Manager)** (necesita el plugin de Session Manager en tu equipo):

```bash
aws ssm start-session --region us-east-2 --target ID_DE_LA_EC2
sudo tail -n 50 /var/log/nodo-ruta-arranque.log   # arranque (user data)
sudo docker ps; sudo docker logs --tail 50 app    # registros de la app
sudo bash /opt/nodo-ruta/repo/despliegue/aws/respaldar.sh   # respaldo manual a S3
```

**Pruebas medidas (caida, respaldo a S3, restauracion, destruccion):** paso a paso en [PRUEBAS.md](PRUEBAS.md).

**Probar la caida de una instancia (version corta):** `aws ec2 stop-instances --region us-east-2 --instance-ids ID` y sondear el ALB con `scripts/verificar_servicio.py` o `curl` en bucle, anotando las marcas de tiempo (el health check tarda ~10 s en sacarla; puede haber algunos 502).

**Destruir:** primero esta pila (`delete-stack` de `nodo-ruta-computo`), luego `02` y `01` (ver arriba); si no se destruye, sigue cobrando.

**Pendiente / limites:** sin HTTPS (no hay dominio); sin CloudWatch Logs (los registros se ven con `docker logs` por SSM); restaurar desde S3 tiene script (`despliegue/aws/datos.sh`) pero aun no esta probado en AWS; la base RDS sigue siendo punto unico de falla.
