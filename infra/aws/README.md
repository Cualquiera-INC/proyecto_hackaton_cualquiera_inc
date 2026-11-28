# infra/aws - plantillas de CloudFormation

Todo va en **us-east-2 (Ohio)**: es la unica region que permite la politica de la organizacion (EC2, CloudFormation, RDS, ELB, ECS). Cada comando lleva `--region us-east-2`. Decisiones: D13 y D14 en `docs/03-decisiones.md`; diagrama en `docs/02-arquitectura.md`.

## Despliegue en un comando

`scripts/aws_nodo.py` automatiza todo lo de este documento y de [PRUEBAS.md](PRUEBAS.md) (D17): secretos en SSM, las 4 pilas en orden, el front, la espera a que el ALB vea sanas las 2 EC2, la prueba de humo y la destruccion. Solo usa la biblioteca estandar de Python y llama al AWS CLI (macOS, Windows y Linux; sin bash). Requiere AWS CLI v2 con credenciales activas, `git` y `npm`. La region es siempre us-east-2.

```bash
python scripts/aws_nodo.py estado                       # pilas, URLs, salud del target group, parametros SSM, aviso de costo
python scripts/aws_nodo.py desplegar                    # crea o actualiza todo y prueba (RDS y CloudFront tardan varios minutos; el script mide cada paso)
python scripts/aws_nodo.py probar                       # humo + respaldo a S3 por SSM (sin pruebas destructivas)
python scripts/aws_nodo.py destruir                     # pide escribir "destruir"; --si lo omite
python scripts/aws_nodo.py --simular desplegar          # solo lecturas: muestra lo que ejecutaria
```

Opciones utiles: `desplegar --cidr X.X.X.X/32` (por defecto tu IP publica), `desplegar --publico` (CloudFront responde a cualquier IP; ver mas abajo), `--version COMMIT` (por defecto `origin/main`; debe estar en GitHub porque las EC2 lo clonan), `--permitir-reemplazo`, `--evidencia AWS09` (guarda la bitacora con marcas de tiempo en `evidencias/AWS09_despliegue_<fecha>.txt`; tambien en `probar` y `destruir`) y `destruir --conservar-secretos`.

Que hace `desplegar`, en orden: (1) prechequeos: identidad, git sin cambios pendientes en lo que se despliega y commit publicado en GitHub; (2) `CidrAcceso`; (3) secretos `/nodo-ruta/db/password` y `/nodo-ruta/front/clave-origen` en SSM SecureString, **creados solo si faltan** y nunca impresos; (4) pilas 01, 02, 03, 04; (5) espera a que los 2 destinos esten `healthy` (maximo 15 min); (6) `scripts/publicar_front.py`; (7) prueba de humo por CloudFront (`/` HTML, `/pedidos` con 6 pedidos, `/health` desde las dos zonas). Termina con la duracion de cada paso y el total.

- **Idempotente.** Repetirlo no rompe nada: si una pila no existe se crea; si existe se actualiza con un conjunto de cambios (change set) y **se aborta si algun recurso se reemplazaria** (Replacement `True` o `Conditional`: por ejemplo una AMI mas nueva o un `--version` distinto cambian el user data de las EC2) salvo `--permitir-reemplazo`. "Sin cambios" cuenta como exito. Una pila en `ROLLBACK_COMPLETE` se borra y se recrea. En las actualizaciones, los parametros que no cambian usan `UsePreviousValue`.
- **Secretos.** Se pasan a CloudFormation y a SSM por archivos temporales con permisos 0600 en el directorio temporal del sistema, que se borran al terminar: no quedan en la linea de comandos, en el historial ni en el repo. La clave de origen vive en SSM, asi que `desplegar` puede repetirse desde otra terminal.
- **Fallos.** Se imprimen los eventos `FAILED` de la pila (recurso y motivo) y el codigo de salida es 1.
- **Destruccion.** Vacia el bucket del front, borra 04, 03, vacia el bucket de respaldos **con versiones y marcas de borrado**, borra 02, 01 y los parametros SSM, y verifica que no quede nada con `proyecto=nodo-ruta`. Se puede repetir si algo fallo a medias. La API de etiquetas esta bloqueada por la politica de la organizacion en us-east-1: ahi se revisan las distribuciones de CloudFront con `list-distributions`. Quedan a proposito el rol `github-actions-nodo-ruta` y el proveedor OIDC.

## Despliegue desde GitHub Actions

El workflow `.github/workflows/aws.yml` ejecuta este mismo script sin claves guardadas: GitHub pide un pase OIDC y asume el rol `github-actions-nodo-ruta` (ARN en la variable del repo `AWS_ROLE_ARN`). Los permisos del rol estan en [iam/politica-github-actions.json](iam/README.md) y **hay que aplicarlos una vez a mano** (el rol hoy no tiene ninguno); sin eso el workflow falla en el primer comando.

**Como lanzarlo:** pestaña *Actions* > *AWS Nodo Ruta* > *Run workflow*, con la rama `main` (solo corre desde ahi: el rol confia unicamente en `main`, asi que primero hay que integrar los cambios).

| Entrada | Uso |
|---|---|
| `accion` | `estado`, `desplegar`, `probar` o `destruir` |
| `cidr` | Obligatorio para `desplegar`: **tu IP publica con `/32`** (la ves en https://checkip.amazonaws.com; ej. `203.0.113.7/32`). Es la unica que podra abrir la app por CloudFront o el ALB. Se rechaza `0.0.0.0/0` y cualquier formato distinto. **No es la IP del runner** |
| `publico` | Solo `desplegar`: `no` (por defecto) deja CloudFront restringido a `cidr`; `si` lo abre a cualquier IP para el pitch (D18). El ALB **no** se abre: sigue admitiendo solo CloudFront y `cidr`. Un despliegue con `no` vuelve a cerrarlo |
| `version` | Opcional: commit a desplegar (por defecto el de `main`). Debe estar en GitHub, las EC2 lo clonan |
| `confirmacion` | Para `destruir`: escribir exactamente `destruir` |

- **Cuanto tarda:** `desplegar` ~45 min (RDS ~13 min y CloudFront ~7 min); `destruir` ~10 min; `estado` y `probar`, pocos minutos. El limite del job es 90 min. La sesion de AWS dura **1 hora como maximo** (`MaxSessionDuration` del rol = 3600): si un despliegue pasara de ahi, fallaria por credenciales vencidas; las pilas siguen en AWS, se repite `desplegar` y continua (es idempotente).
- **Una ejecucion a la vez:** `concurrency: aws-nodo-ruta`, sin cancelar la que esta en curso.
- **Prueba de humo (`publico=no`):** el runner no es tu IP, asi que CloudFront le responde 403 (eso comprueba la restriccion). Por eso, dentro de Actions la comprobacion de `/health` y `/pedidos` se hace por SSM en cada EC2 (`--humo-remoto`, automatico con `GITHUB_ACTIONS`).
- **Prueba de humo (`publico=si`):** CloudFront responde 200 a cualquier IP, asi que el runner prueba `/`, `/pedidos` y `/health` directamente por CloudFront.
- **Resultado:** resumen en la pagina de la ejecucion (URL de CloudFront y estado) y la bitacora con marcas de tiempo como artifact `bitacora-aws-<id>` (30 dias).
- **Cuidado:** el repo es publico, asi que tu IP y el id de cuenta aparecen en los registros y en el artifact. AWS ya oculta el id de cuenta en el registro; la IP no se oculta.
- `destruir` ya no cuenta como pendientes las instancias `terminated` ni el snapshot automatico de RDS (AWS los limpia solo; ver AWS07): los lista como "resto esperado".

**Modo publico (D18).** `04-front.yaml` tiene el parametro `AccesoPublico` (`si`/`no`, por defecto `no`). Con `si`, la distribucion no asocia la CloudFront Function de IP; `CidrAcceso` sigue siendo obligatorio (/32, tu IP para entrar directo al ALB) y los candados que prohiben `0.0.0.0/0` en red y computo siguen vigentes. Desde terminal: `python scripts/aws_nodo.py desplegar --publico`; `estado` muestra si CloudFront es PUBLICO o RESTRINGIDO. Cambiar el parametro en una pila existente solo toca `FunctionAssociations` (sin interrupcion): no reemplaza la distribucion ni el bucket; el change set del script lo verifica. Riesgos y mitigaciones: D18. Destruye todo el mismo dia. Estado: escrito, **sin probar en AWS**.

Las pruebas de caida de una instancia y de restauracion siguen siendo manuales (PRUEBAS.md). Lo que sigue en este documento son los **pasos manuales, como referencia** de lo que automatiza el script.

## Que crea cada plantilla

| Plantilla | Estado | Crea | Costo |
|---|---|---|---|
| `01-red.yaml` | **desplegada** como `nodo-ruta-red` (23-11, evidencia AWS01) | VPC propia (`10.20.0.0/16`), 2 subredes publicas (ALB y EC2) y 2 privadas (RDS) en 2 zonas, Internet Gateway, tablas de rutas y los grupos de seguridad ALB -> EC2 (8080) -> RDS (5432) | **Gratis** (sin NAT Gateway ni IP elasticas) |
| `02-datos.yaml` | **desplegada** como `nodo-ruta-datos` (23-11, evidencia AWS02) | RDS PostgreSQL 17 Single-AZ (`db.t4g.micro`, 20 GB gp2, cifrada, sin acceso publico) en las subredes privadas y bucket S3 de respaldos (versiones, cifrado, expiracion a 7 dias) | **RDS y S3 consumen creditos** (ver nota de costo) |
| `03-computo.yaml` | **desplegada** como `nodo-ruta-computo`; D16 la actualiza (listener 403 + reglas, ver abajo) | 2 EC2 (app + pedidos en contenedores), ALB HTTP, target group con health check a `/health`, rol IAM de minimo privilegio con SSM | **EC2, ALB e IPv4 publicas consumen creditos** (ver nota de costo) |
| `04-front.yaml` | **desplegada** como `nodo-ruta-front` (23-11, evidencia AWS08; distribucion creada en 6 min 54 s) | Bucket S3 privado + distribucion de CloudFront (HTTPS) que sirve la interfaz y envia `/pedidos` y `/health` al ALB, con una CloudFront Function que solo deja pasar a `CidrAcceso` | **Dentro del plan gratuito de CloudFront** (ver `docs/04`); el bucket cuesta centavos |

Las EC2 van en subredes publicas con IP publica (para bajar imagenes y usar SSM sin NAT) pero su grupo de seguridad solo acepta el puerto 8080 desde el ALB y no tiene SSH. Las plantillas siguientes toman los valores con `Fn::ImportValue` de los exports `<nombre-de-la-pila>-VpcId`, `-SubredesPublicas`, `-SubredesPrivadas` (listas separadas por coma; usar `Fn::Split`), `-SgAlb`, `-SgEc2` y `-SgRds`.

## Orden de despliegue

1. `01-red.yaml` (nombre de pila sugerido: `nodo-ruta-red`)
2. `02-datos.yaml`
3. `03-computo.yaml`
4. `04-front.yaml` (pila `nodo-ruta-front`, importa `nodo-ruta-computo-DnsAlb`)

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
    ParameterKey=ClaveOrigen,ParameterValue=$CLAVE_ORIGEN ParameterKey=CidrAcceso,ParameterValue=TU_IP/32 \
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

Solo responde a `CidrAcceso` (la IP de la pila de red). Si el ALB no contesta, revisar que tu IP no haya cambiado. Desde D16 el listener devuelve **403** por defecto: pasa quien trae el encabezado `X-Origin-Verify` (CloudFront) o llega desde `CidrAcceso`, asi que estas pruebas directas siguen funcionando. `ClaveOrigen` es un parametro nuevo y obligatorio (ver la pila del front: se genera con `openssl rand -hex 24`, no se guarda en ningun archivo).

**Entrar a una EC2 (sin SSH, por SSM Session Manager)** (necesita el plugin de Session Manager en tu equipo):

```bash
aws ssm start-session --region us-east-2 --target ID_DE_LA_EC2
sudo tail -n 50 /var/log/nodo-ruta-arranque.log   # arranque (user data)
sudo docker ps; sudo docker logs --tail 50 app    # registros de la app
sudo bash /opt/nodo-ruta/repo/despliegue/aws/respaldar.sh   # respaldo manual a S3
```

**Pruebas medidas (caida, respaldo a S3, restauracion, destruccion):** paso a paso en [PRUEBAS.md](PRUEBAS.md).

**Probar la caida de una instancia (version corta):** `aws ec2 stop-instances --region us-east-2 --instance-ids ID` y sondear el ALB con `scripts/verificar_servicio.py` o `curl` en bucle, anotando las marcas de tiempo (el health check tarda ~10 s en sacarla; puede haber algunos 502).

**Destruir:** primero `nodo-ruta-front` (vaciando su bucket, ver AWS07 en PRUEBAS.md), luego esta pila (`nodo-ruta-computo`), luego `02` y `01`; si no se destruye, sigue cobrando.

**Pendiente / limites:** HTTPS solo entre el visitante y CloudFront (de CloudFront al ALB va en HTTP, D16); sin CloudWatch Logs (los registros se ven con `docker logs` por SSM); restaurar desde S3 con `despliegue/aws/datos.sh` esta probado en AWS (AWS06b: 8,6 s); la base RDS sigue siendo punto unico de falla.

## Pila del front (`04-front.yaml`, pila `nodo-ruta-front`) - D16

Sirve la interfaz (`frontend-nodo/`) desde un bucket S3 privado a traves de CloudFront y envia `/pedidos` y `/health` al ALB, con un solo dominio `https://<id>.cloudfront.net`. **Estado: desplegada y probada (AWS08, 23-11).** Cambia tambien `01-red.yaml` (el grupo del ALB acepta la prefix list de CloudFront en el puerto 80) y `03-computo.yaml` (listener con 403 por defecto, regla por clave de origen y regla por IP, salida `DnsAlb`). Las dos son **actualizaciones in situ** de pilas existentes: no reemplazan el ALB, el target group ni las EC2.

**Que propiedades podrian causar reemplazo y como se evita:**

- `SgAlb`: solo cambia `SecurityGroupIngress` (sin interrupcion). `GroupDescription` y `VpcId` no se tocan (cambiarlos reemplazaria el grupo y arrastraria al ALB y a las EC2).
- `Listener`: solo cambia `DefaultActions` (sin interrupcion); las reglas son recursos nuevos.
- Las EC2 no cambian, **salvo que `AmiX86`/`AmiArm` se vuelvan a resolver** a una AMI mas nueva (parametros de SSM): eso cambiaria `ImageId` y reemplazaria las EC2. Por eso la actualizacion pasa `UsePreviousValue` en **todos** los parametros viejos, y antes se revisa el conjunto de cambios (Replacement debe ser `False` o vacio).

Los bloques se pegan en zsh de macOS desde la raiz del repo. Cada uno depende del anterior (misma terminal).

**a) Preparar la terminal.** `ClaveOrigen` vive solo en la variable de la terminal; si cierras la terminal se pierde, pero las pilas la recuerdan (en futuras actualizaciones usa `UsePreviousValue`). `CIDR` se toma de la pila de red, para usar el mismo valor en las tres.

```bash
cd ~/Develop/proyecto_hackaton_cualquiera_inc
export AWS_DEFAULT_REGION=us-east-2
marca() { date +%Y-%m-%dT%H:%M:%S; }
salida() { aws cloudformation describe-stacks --stack-name "$1" --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text; }
CLAVE_ORIGEN=$(openssl rand -hex 24)
CIDR=$(aws cloudformation describe-stacks --stack-name nodo-ruta-red --query "Stacks[0].Parameters[?ParameterKey=='CidrAcceso'].ParameterValue" --output text)
EC2_A_ANTES=$(salida nodo-ruta-computo IdInstanciaA)
EC2_B_ANTES=$(salida nodo-ruta-computo IdInstanciaB)
echo "clave de ${#CLAVE_ORIGEN} caracteres; CIDR=$CIDR; EC2 $EC2_A_ANTES $EC2_B_ANTES"
```

Debe decir 48 caracteres, tu IP con `/32` y dos ids de EC2. Si algo sale vacio, no sigas.

**b) Actualizar la red** (agrega la regla de la prefix list; `pl-b6a144df` es la de us-east-2):

```bash
aws cloudformation update-stack --stack-name nodo-ruta-red --template-body file://infra/aws/01-red.yaml --parameters ParameterKey=CidrAcceso,UsePreviousValue=true ParameterKey=CidrVpc,UsePreviousValue=true ParameterKey=PrefixListCloudFront,ParameterValue=pl-b6a144df
aws cloudformation wait stack-update-complete --stack-name nodo-ruta-red
aws ec2 describe-security-groups --group-ids $(salida nodo-ruta-red SgAlb) --query "SecurityGroups[0].IpPermissions[].[FromPort,IpRanges[0].CidrIp,PrefixListIds[0].PrefixListId]" --output text
```

Deben verse dos reglas de puerto 80: tu CIDR y la prefix list. Si `update-stack` falla por el limite de reglas del grupo, no hay cambios (la pila revierte sola).

**c) Revisar y actualizar el computo.** Primero un conjunto de cambios solo para mirar (no modifica nada); la ultima columna debe ser `False` para los recursos existentes y solo aparecer `Add` para las dos reglas:

```bash
PARAMS_COMPUTO="ParameterKey=PilaRed,UsePreviousValue=true ParameterKey=PilaDatos,UsePreviousValue=true ParameterKey=VersionGit,UsePreviousValue=true ParameterKey=UrlRepo,UsePreviousValue=true ParameterKey=TipoInstancia,UsePreviousValue=true ParameterKey=AmiX86,UsePreviousValue=true ParameterKey=AmiArm,UsePreviousValue=true ParameterKey=CidrAcceso,ParameterValue=$CIDR"
aws cloudformation create-change-set --stack-name nodo-ruta-computo --change-set-name d16-revision --template-body file://infra/aws/03-computo.yaml --capabilities CAPABILITY_IAM --parameters ${=PARAMS_COMPUTO} ParameterKey=ClaveOrigen,ParameterValue=$CLAVE_ORIGEN
aws cloudformation wait change-set-create-complete --stack-name nodo-ruta-computo --change-set-name d16-revision
aws cloudformation describe-change-set --stack-name nodo-ruta-computo --change-set-name d16-revision --query "Changes[].ResourceChange.[LogicalResourceId,Action,Replacement]" --output text
```

Esperado: `Listener Modify False`, `ReglaOrigenCloudFront Add`, `ReglaIpPermitida Add`. **Si aparece `True`, `Conditional` o alguna EC2 (`Ec2A`, `Ec2B`), NO continues**: borra el conjunto con `aws cloudformation delete-change-set --stack-name nodo-ruta-computo --change-set-name d16-revision` y avisa. Si todo esta bien, borrar el conjunto de revision y actualizar de verdad:

```bash
aws cloudformation delete-change-set --stack-name nodo-ruta-computo --change-set-name d16-revision
aws cloudformation update-stack --stack-name nodo-ruta-computo --template-body file://infra/aws/03-computo.yaml --capabilities CAPABILITY_IAM --parameters ${=PARAMS_COMPUTO} ParameterKey=ClaveOrigen,ParameterValue=$CLAVE_ORIGEN
aws cloudformation wait stack-update-complete --stack-name nodo-ruta-computo
echo "A: $EC2_A_ANTES -> $(salida nodo-ruta-computo IdInstanciaA)"
echo "B: $EC2_B_ANTES -> $(salida nodo-ruta-computo IdInstanciaB)"
ALB=$(salida nodo-ruta-computo UrlAlb)
curl -s -o /dev/null -w "ALB directo /pedidos: %{http_code}\n" "$ALB/pedidos"
curl -s -o /dev/null -w "ALB directo /health: %{http_code}\n" "$ALB/health"
```

Los ids de antes y despues deben ser **iguales** (las EC2 no se reemplazaron) y los dos `curl` deben dar 200 (entras por la regla de tu IP).
**d) Crear el front** midiendo cuanto tarda la distribucion (CloudFront suele tardar varios minutos; se guarda la salida como evidencia):

```bash
P=evidencias/AWS08_front_creacion
echo "$(marca) crear nodo-ruta-front" | tee "$P".txt
aws cloudformation create-stack --stack-name nodo-ruta-front --template-body file://infra/aws/04-front.yaml --parameters ParameterKey=ClaveOrigen,ParameterValue=$CLAVE_ORIGEN ParameterKey=CidrAcceso,ParameterValue=$CIDR --tags Key=proyecto,Value=nodo-ruta
aws cloudformation wait stack-create-complete --stack-name nodo-ruta-front
echo "$(marca) front lista (CREATE_COMPLETE)" | tee -a "$P".txt
aws cloudformation describe-stacks --stack-name nodo-ruta-front --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" --output text | tee -a "$P".txt
```

Si falla (la politica de la organizacion nunca se probo contra CloudFront), mira el motivo con el bloque siguiente, borra la pila fallida y reporta el error tal cual:

```bash
aws cloudformation describe-stack-events --stack-name nodo-ruta-front --query "StackEvents[?contains(ResourceStatus,'FAILED')].[LogicalResourceId,ResourceStatusReason]" --output text
```

**e) Publicar la interfaz.** El script construye con Node (`npm ci` y `npm run build`, con `VITE_API_URL` vacio), sube `assets/` con cache de un anio, sube el resto con `no-cache` e invalida `/index.html` y `/`. Con `--simular` solo lee las salidas de la pila y muestra los comandos:

```bash
python3 scripts/publicar_front.py 2>&1 | tee evidencias/AWS08_publicacion.txt
```

**f) Comprobar** con la seccion **AWS08** de [PRUEBAS.md](PRUEBAS.md). Si cambia tu IP, hay que actualizar las **tres** pilas con el nuevo `CidrAcceso` (y la regla de la funcion se actualiza sola con la pila del front).

**Modo publico (D18):** con `AccesoPublico=si` el parametro `CidrAcceso` de esta pila solo se usa en la funcion (que no se asocia); para manual: agrega `ParameterKey=AccesoPublico,ParameterValue=si` a `update-stack` con `UsePreviousValue` en los demas parametros, y `no` para volver a cerrar.

**Limites reconocidos (D16):** el tramo CloudFront -> ALB va en HTTP; el ALB queda abierto a todas las IP de CloudFront (el grupo de seguridad no distingue a cual distribucion) y se mitiga con la clave `X-Origin-Verify` mas la funcion de IP en el borde; la clave es visible para quien pueda leer las reglas del ALB. `SgAlb` queda con 56 de 60 reglas posibles (la prefix list pesa 55): no se le pueden agregar mas reglas sin pedir cuota.
