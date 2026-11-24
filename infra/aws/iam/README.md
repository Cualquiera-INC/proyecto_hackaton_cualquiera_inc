# infra/aws/iam - permisos del rol de GitHub Actions

`politica-github-actions.json` es la politica de permisos (inline) del rol `github-actions-nodo-ruta`, el que asume `.github/workflows/aws.yml` por OIDC. **Esta en el repo para revisarla; no se aplica sola.** Hoy el rol no tiene permisos.

## Aplicarla (lo hace una persona con permisos de IAM, tras revisarla)

```bash
aws iam put-role-policy --role-name github-actions-nodo-ruta --policy-name nodo-ruta-despliegue \
  --policy-document file://infra/aws/iam/politica-github-actions.json
```

Quitarla: `aws iam delete-role-policy --role-name github-actions-nodo-ruta --policy-name nodo-ruta-despliegue`. Validada con IAM Access Analyzer `ValidatePolicy` (IDENTITY_POLICY): 0 hallazgos. Pesa 9.7 mil caracteres de los 10 240 que admite un rol en politicas inline: **casi no queda margen**; si hay que agregar permisos, usar una segunda politica o convertir acciones sueltas en comodines de solo lectura.

## Por que existe cada bloque

CloudFormation actua con los permisos del propio rol (las pilas no usan un rol de servicio), asi que el rol necesita los permisos de todos los recursos de las plantillas 01 a 04.

| Bloque (`Sid`) | Que permite | Por que |
|---|---|---|
| `CloudFormationPilas` | Crear, actualizar, borrar y revisar solo `stack/nodo-ruta-*` y los change sets `aws-nodo-*` | Es lo que hace `aws_nodo.py` (change set revisado antes de ejecutar) |
| `CloudFormationLecturaGeneral` | `ValidateTemplate`, `ListStacks`, `ListExports`, `DescribeStacks` sin nombre | No admiten recurso concreto; `estado` y la revision de restos los usan |
| `SinResourceLevelLecturas` | `sts:GetCallerIdentity` | Prechequeo de identidad |
| `EtiquetasLectura` | `tag:GetResources` en us-east-1 y us-east-2 | Verificar que `destruir` no deja nada con `proyecto=nodo-ruta`. La SCP la niega en us-east-1 y el script usa un plan B |
| `Ec2Lectura` | `ec2:Describe*` | Solo lectura; ALB, RDS y CloudFormation la necesitan y no admite recurso concreto |
| `Ec2Red` | VPC, subredes, IGW, rutas, grupos de seguridad y etiquetas | Plantilla 01. `Resource "*"` porque los ids no existen aun al crear; limitado a us-east-2 |
| `Ec2CrearInstancias` | `RunInstances`, `ModifyInstanceAttribute` | Plantilla 03 (2 EC2) |
| `Ec2OperarSoloEtiquetadas` | Terminar, iniciar y parar solo instancias con `proyecto=nodo-ruta` | Borrado de la pila 03 y rollbacks; no toca otras EC2 de la cuenta |
| `PasarRolAInstancias` | `iam:PassRole` solo hacia `role/nodo-ruta-computo-*` y solo a `ec2.amazonaws.com` | Perfil de instancia de la pila 03; sin esto, `RunInstances` con rol seria una via a cualquier rol |
| `IamRolEc2`, `IamPoliticaGestionadaSoloSsm`, `IamPerfilEc2` | Crear y borrar el rol y el perfil `nodo-ruta-computo-*` (CloudFormation les pone ese prefijo); adjuntar **solo** `AmazonSSMManagedInstanceCore` | Plantilla 03. Sin `iam:*` ni acceso a otros roles |
| `IamRolesDeServicioElbRds` | `CreateServiceLinkedRole` solo para ELB y RDS | Por si la cuenta es nueva y aun no existen (hoy ya existen) |
| `ElbLectura`, `ElbGestion` | ALB, target group, listener y reglas | Plantilla 03. Los nombres los genera CloudFormation, por eso `Resource "*"` con region |
| `RdsLectura`, `RdsGestion` | Instancia `nodo-ruta-*`, subnet group `nodo-ruta-*`, y los grupos de parametros y opciones por defecto | Plantilla 02 |
| `S3BucketsDelProyecto`, `S3ObjetosDelProyecto`, `S3ListarBuckets` | Buckets y objetos `nodo-ruta-*` (crear, configurar, vaciar con versiones, borrar) | Plantillas 02 y 04, `publicar_front.py` y `destruir` |
| `CloudFront*` | Distribuciones, OAC, funciones `nodo-ruta-*`, invalidaciones y listados | Plantilla 04. Servicio global: sin condicion de region; los ids no se conocen de antemano |
| `Ssm*` | Parametros `/nodo-ruta/*`, AMI publicas de AL2023, `SendCommand` con `AWS-RunShellScript` solo a instancias con `proyecto=nodo-ruta`, y consultar su resultado | Secretos, AMI de la plantilla 03 y `probar` (respaldo y prueba local por SSM) |
| `KmsSoloPorSsm` | Cifrar y descifrar solo a traves de SSM (`kms:ViaService`) | SecureString con la clave `aws/ssm`; es un refuerzo, normalmente la clave ya lo permite |

Restriccion de region: todo lo regional lleva `aws:RequestedRegion = us-east-2` (y us-east-1 solo para `tag:GetResources`). Quedan sin ella solo IAM, CloudFront y STS, que son globales.

## Riesgos que se aceptan (y por que son pocos)

- Quien pueda lanzar el workflow puede crear recursos de pago en us-east-2 (EC2, RDS, ALB, CloudFront). Mitiga: solo corre desde `main`, el rol solo confia en `main`, y hay presupuesto con alertas.
- `PutRolePolicy` sobre `nodo-ruta-computo-*` permite cambiar los permisos de las EC2. Son roles que solo asume EC2; no se puede tocar ningun otro rol.
- Muchas acciones de EC2, ELB y CloudFront usan `Resource "*"` porque sus ids no se conocen antes de crear. No hay `*:*` ni `iam:*`.
- Si la primera ejecucion falla con `AccessDenied`, el mensaje nombra la accion que falta; agregarla al bloque que corresponda y volver a aplicar.
