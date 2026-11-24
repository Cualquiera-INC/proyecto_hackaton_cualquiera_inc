# Pruebas medidas en AWS (us-east-2)

Guía para ejecutar AWS04 a AWS08 sobre las pilas `nodo-ruta-red`, `nodo-ruta-datos` y `nodo-ruta-computo` ya creadas (AWS01 a AWS03 están en `EVIDENCIAS.md`). Todo es **solo datos sintéticos** y se hace desde la raíz del repo, en **zsh de macOS**: los bloques se pegan completos, no tienen líneas de comentario y no usan `read -p`. Las explicaciones están fuera de los bloques.

Reglas que se mantienen: región solo `us-east-2`, nada de pruebas destructivas sin respaldo previo en S3 (regla 5), los tiempos salen de marcas de tiempo (regla 7) y si una prueba falla se reporta tal cual (con la salida real) en `EVIDENCIAS.md`. Cada bloque guarda su salida en `evidencias/AWS0x_...` (las marcas llevan la **hora local del Mac**, la misma que escribe `scripts/monitorear.py`). Los scripts se niegan a sobrescribir un archivo existente: si repites una prueba, cambia el prefijo (por ejemplo `AWS04b_`).

Los umbrales de CUMPLE de abajo son **nuestros criterios** [S]; el reto no fija cifras.

## 0. Preparación (una vez por terminal)

Define las variables y tres funciones: `marca` (hora local), `salida` (lee salidas de la pila) y `ssm` (ejecuta un comando en una EC2 con `AWS-RunShellScript` y muestra estado, salida y error). `ssm` pide `ssm:SendCommand`, que tu rol de administrador ya tiene; los comandos que le pases no deben llevar comillas dobles ni barras invertidas.

```bash
cd ~/Develop/proyecto_hackaton_cualquiera_inc
export AWS_DEFAULT_REGION=us-east-2
marca() { date +%Y-%m-%dT%H:%M:%S; }
salida() { aws cloudformation describe-stacks --stack-name "$1" --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text; }
ALB=$(salida nodo-ruta-computo UrlAlb)
EC2_A=$(salida nodo-ruta-computo IdInstanciaA)
EC2_B=$(salida nodo-ruta-computo IdInstanciaB)
TG=$(salida nodo-ruta-computo ArnGrupoDestino)
BUCKET=$(salida nodo-ruta-datos BucketNombre)
ssm() {
  local id
  id=$(aws ssm send-command --instance-ids "$1" --document-name AWS-RunShellScript --parameters "{\"commands\":[\"$2\"]}" --query Command.CommandId --output text) || return 1
  sleep 3
  aws ssm wait command-executed --command-id "$id" --instance-id "$1"
  echo "estado: $(aws ssm get-command-invocation --command-id "$id" --instance-id "$1" --query Status --output text)"
  aws ssm get-command-invocation --command-id "$id" --instance-id "$1" --query StandardOutputContent --output text
  aws ssm get-command-invocation --command-id "$id" --instance-id "$1" --query StandardErrorContent --output text
}
echo "$ALB $EC2_A $EC2_B $BUCKET"
aws elbv2 describe-target-health --target-group-arn "$TG" --query "TargetHealthDescriptions[].[Target.Id,TargetHealth.State]" --output text
```

Debes ver las URL, los dos ids y las dos instancias en `healthy`. Si falta alguno, no sigas. Si el ALB no contesta, tu IP pública cambió (el ALB solo acepta la de `CidrAcceso`): ver `infra/aws/README.md`.

## AWS04 - Caída de una instancia (EC2 B) y recuperación

**Objetivo.** Medir qué ve un cliente cuando una de las dos EC2 se detiene: cuántas solicitudes fallan y en qué ventana, cuánto tarda el ALB en dejar de mandarle tráfico, y cuánto tarda B en volver a responder tras arrancarla sin hacer nada más. Esto prueba **tolerancia a la caída de una instancia** (no alta disponibilidad: la base RDS sigue siendo un punto único de falla).

**Por qué B vuelve sola (leído en el código, a verificar con la medición).** `infra/aws/03-computo.yaml` instala Docker con `systemctl enable --now docker` y `despliegue/aws/iniciar.sh` crea `app` y `pedidos` con `--restart unless-stopped`. El user data solo corre en el primer arranque (no se repite al reiniciar), pero Docker arranca con el sistema y levanta los contenedores. La clave de la base está en `/etc/nodo-ruta/db_password` en el disco EBS, que se conserva al detener. La IP pública de la EC2 cambia al arrancar, pero el ALB la registra por id de instancia, así que no importa. Es el comportamiento esperado; la prueba lo confirma o lo desmiente.

**Línea de tiempo prevista.** Se lanza el monitor 270 s (el reto pide ~180 s; se alarga porque detener y arrancar una EC2 toma tiempo). A los 20 s se detiene B, se espera a que quede `stopped`, se deja 30 s detenida, se arranca y se espera hasta el final. En paralelo, un segundo bucle anota el estado de salud de ambos destinos cada ~2 s.

```bash
P=evidencias/AWS04_caida_instancia
echo "$(marca) inicio; B=$EC2_B" | tee "$P"_marcas.txt
python3 scripts/monitorear.py "${ALB%/}/pedidos" --segundos 270 --intervalo 0.5 --salida "$P"_monitor.json > "$P"_monitor.txt 2>&1 &
MON=$!
( while true; do echo "$(marca) $(aws elbv2 describe-target-health --target-group-arn "$TG" --query "TargetHealthDescriptions[].[Target.Id,TargetHealth.State]" --output text | tr '\t\n' '  ')"; sleep 2; done ) > "$P"_salud_alb.txt 2>&1 &
SAL=$!
sleep 20
echo "$(marca) STOP_B enviado" | tee -a "$P"_marcas.txt
aws ec2 stop-instances --instance-ids "$EC2_B" --query "StoppingInstances[0].CurrentState.Name" --output text | tee -a "$P"_marcas.txt
aws ec2 wait instance-stopped --instance-ids "$EC2_B"
echo "$(marca) B en estado stopped" | tee -a "$P"_marcas.txt
sleep 30
echo "$(marca) START_B enviado" | tee -a "$P"_marcas.txt
aws ec2 start-instances --instance-ids "$EC2_B" --query "StartingInstances[0].CurrentState.Name" --output text | tee -a "$P"_marcas.txt
aws ec2 wait instance-running --instance-ids "$EC2_B"
echo "$(marca) B en estado running" | tee -a "$P"_marcas.txt
wait $MON
kill $SAL
echo "$(marca) fin" | tee -a "$P"_marcas.txt
```

El comando termina solo (~4,5 min). El monitor devuelve código 1 si hubo errores: es esperable y no es un fallo del bloque. Después, el resumen y las ventanas:

```bash
P=evidencias/AWS04_caida_instancia
cat "$P"_marcas.txt
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d.pop("detalle"); print(json.dumps(d,ensure_ascii=False,indent=2))' "$P"_monitor.json | tee "$P"_resumen.txt
python3 -c 'import json,sys; [print(r["fecha"],r["http"],r.get("error","")[:70]) for r in json.load(open(sys.argv[1]))["detalle"] if r.get("http")!=200]' "$P"_monitor.json | tee "$P"_errores.txt
grep -n "unhealthy\|unused\|draining\|initial" "$P"_salud_alb.txt | sed -n '1p;$p'
```

Cómo leer los números (todo en hora local):

- **Solicitudes totales y errores:** `consultas` y `errores` del resumen.
- **Ventana de errores:** `primer_error` y `ultimo_error`, comparados con la marca `STOP_B enviado`.
- **Tiempo hasta que el ALB deja de mandarle tráfico:** `ultimo_error` menos `STOP_B enviado` (a partir de ahí todo va a A), y la primera línea de `_salud_alb.txt` donde B deja de estar `healthy`. Con 2 fallos de 5 s se espera ~10 s [E: plantilla 03-computo].
- **Tiempo hasta que B vuelve a responder:** en `instancias`, la `ultima` de B antes del silencio y su `mayor_silencio.hasta` (primera respuesta de B tras arrancar), menos la marca `START_B enviado`.

**CUMPLE (criterio nuestro [S]) si:** (1) todas las respuestas posteriores a la última de B vienen de A hasta que B reaparece; (2) todos los errores caen en una ventana corta alrededor de `STOP_B enviado` (esperado: pocos segundos más el health check de ~10 s) y **después no hay más errores**, también al reaparecer B; (3) `_salud_alb.txt` muestra B saliendo y volviendo a `healthy` sin ninguna acción tuya aparte de `stop` y `start`; (4) B responde de nuevo antes de terminar los 270 s. Si algo no se cumple (por ejemplo B no vuelve porque los contenedores no arrancan), se reporta con la salida y se revisa por SSM con `docker ps` y `/var/log/nodo-ruta-arranque.log`.

## AWS05 - Respaldo a S3 y comprobación de integridad

**Objetivo.** Comprobar que `despliegue/aws/respaldar.sh` genera un `pg_dump` de RDS, lo sube a S3 fuera del cómputo con su SHA-256 y que el objeto es íntegro y legible.

**Cómo se llama el script por SSM.** SSM ejecuta como root y sin sesión interactiva: el script define `HOME`, lee `/etc/nodo-ruta.env` (`REGION`, `BUCKET`, `DB_*`), usa la ruta del repo `/opt/nodo-ruta/repo`, escribe en `/var/tmp/nodo-ruta-respaldos` (ya no en `/tmp`) y sube a `respaldos/`, el único prefijo que permite el rol de la EC2. Revisamos estos puntos leyendo el código; no se ejecutó `send-command` antes de esta prueba.

**Paso previo: actualizar el repo de la EC2 A.** Las EC2 corren el código del commit con el que se creó la pila (`6f5a222`), que no incluye `datos.sh` ni los cambios de `respaldar.sh`. Este comando solo cambia los archivos del repo en el disco (no toca los contenedores en ejecución). La rama debe estar subida a GitHub.

```bash
P=evidencias/AWS05_respaldo_s3
COMMIT=$(git rev-parse HEAD)
git branch -r --contains "$COMMIT"
echo "$(marca) actualizar repo en A a $COMMIT" | tee "$P".txt
ssm "$EC2_A" "git -C /opt/nodo-ruta/repo fetch --depth 1 https://github.com/Cualquiera-INC/proyecto_hackaton_cualquiera_inc.git $COMMIT && git -C /opt/nodo-ruta/repo checkout -q FETCH_HEAD && git -C /opt/nodo-ruta/repo log --oneline -1" | tee -a "$P".txt
```

Si `git branch -r --contains` no lista nada, el commit no está en GitHub: haz `git push` antes. Debe aparecer `estado: Success` y el commit nuevo.

**Respaldo, verificación del objeto y de su integridad:**

```bash
P=evidencias/AWS05_respaldo_s3
echo "$(marca) respaldar" | tee -a "$P".txt
ssm "$EC2_A" "bash /opt/nodo-ruta/repo/despliegue/aws/respaldar.sh" | tee -a "$P".txt
echo "$(marca) objetos en S3 (clave, tamano, fecha)" | tee -a "$P".txt
aws s3api list-objects-v2 --bucket "$BUCKET" --prefix respaldos/ --query "Contents[].[Key,Size,LastModified]" --output table | tee -a "$P".txt
KEY=$(aws s3api list-objects-v2 --bucket "$BUCKET" --prefix respaldos/ --query 'sort_by(Contents[?ends_with(Key, `_manual.dump`)], &LastModified)[-1].Key' --output text)
echo "$(marca) comprobar $KEY" | tee -a "$P".txt
ssm "$EC2_A" "bash /opt/nodo-ruta/repo/despliegue/aws/datos.sh comprobar $KEY" | tee -a "$P".txt
echo "$KEY" | tee -a "$P".txt
```

`datos.sh comprobar` baja el objeto de S3 a la EC2, compara su SHA-256 con el `.sha256` guardado, ejecuta `pg_restore --list` (lee el índice del archivo) y exige que contenga `TABLE DATA public pedidos`. **Deja la variable `KEY` definida: la necesita AWS06.**

**CUMPLE si:** el respaldo termina en `estado: Success` y escribe `Respaldo subido: s3://...`; en S3 hay un `.dump` (tamaño mayor que cero, del orden de KB) y su `.sha256` con fecha de ahora; y `comprobar` imprime `COMPROBADO ...` con el mismo SHA-256 y varios objetos en el índice. Además, los objetos quedaron en S3, **fuera de la EC2 y de RDS**.

## AWS06 - Alteración simulada y restauración desde S3

**Objetivo.** Repetir en AWS lo que ya se probó en local (STG13): dañar los datos, comprobar que el servicio lo detecta y restaurar desde el respaldo de S3, midiendo el tiempo hasta recuperar el servicio.

**Seguridad (regla 5).** Solo se altera la base **sintética** de este despliegue y solo si antes existe un respaldo válido en S3 (AWS05): `datos.sh alterar` vuelve a comprobar el respaldo y se niega si no es válido. `datos.sh restaurar` además guarda un respaldo `prerestauracion` del estado actual en S3 antes de tocar nada, y `pg_restore` corre con `--single-transaction`: o se restaura todo o no cambia nada. **Esta prueba no se ha ejecutado**: el procedimiento y el script están preparados, pero es probable que aparezcan detalles reales al correrlo (por ejemplo permisos de `pg_restore` en RDS); si pasa, se reporta tal cual.

**Qué se espera.** Tras `DROP TABLE pedidos` el servicio de datos responde 503 en `/health`, ambos destinos pasan a `unhealthy` y el ALB responde 503 a todos (en local, STG13 lo midió así). Tras restaurar, vuelven solos a `healthy` (~10 s por los 2 aciertos de 5 s). Se mide con el monitor sobre `/health`.

Requiere la variable `KEY` de AWS05 (si abriste otra terminal, repite el bloque 0 y define `KEY=respaldos/<fecha>_manual.dump`).

```bash
P=evidencias/AWS06_restauracion_s3
echo "$(marca) inicio; respaldo $KEY" | tee "$P".txt
python3 scripts/monitorear.py "${ALB%/}/health" --segundos 200 --intervalo 0.5 --salida "$P"_monitor.json > "$P"_monitor.txt 2>&1 &
MON=$!
sleep 10
echo "$(marca) VERIFICAR antes" | tee -a "$P".txt
ssm "$EC2_A" "bash /opt/nodo-ruta/repo/despliegue/aws/datos.sh verificar" | tee -a "$P".txt
echo "$(marca) ALTERAR (DROP TABLE pedidos)" | tee -a "$P".txt
ssm "$EC2_A" "bash /opt/nodo-ruta/repo/despliegue/aws/datos.sh alterar $KEY" | tee -a "$P".txt
sleep 20
echo "$(marca) /health del ALB tras alterar: $(curl -s -m 5 -o /dev/null -w '%{http_code}' "${ALB%/}/health")" | tee -a "$P".txt
echo "$(marca) RESTAURAR" | tee -a "$P".txt
ssm "$EC2_A" "bash /opt/nodo-ruta/repo/despliegue/aws/datos.sh restaurar $KEY" | tee -a "$P".txt
echo "$(marca) restaurar terminó" | tee -a "$P".txt
wait $MON
echo "$(marca) VERIFICAR despues" | tee -a "$P".txt
ssm "$EC2_A" "bash /opt/nodo-ruta/repo/despliegue/aws/datos.sh verificar" | tee -a "$P".txt
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d.pop("detalle"); print(json.dumps(d,ensure_ascii=False,indent=2))' "$P"_monitor.json | tee "$P"_resumen.txt
```

El monitor dura 200 s; el bloque termina cuando acaba. Para el tiempo de recuperación: **primer 200 en el monitor posterior a la marca `RESTAURAR`** menos esa marca (incluye lo que tarda SSM en lanzar y ejecutar el comando, así que es un máximo para el operador); el último error está en `ultimo_error` del resumen.

**CUMPLE si:** (1) `verificar` antes y después muestra los mismos valores (`version_datos` igual y `pedidos=6`); (2) tras alterar, `/health` del ALB responde 503 (el daño se detecta y no se tapa); (3) `restaurar` imprime `Restaurado desde ...` sin errores y existe un objeto `..._prerestauracion.dump` en S3; (4) el servicio vuelve a responder 200 con `estado: ok` sin otra intervención y se registra el tiempo medido.

**Si algo sale mal.** Repetir `restaurar` con el mismo `KEY` (es seguro repetirlo). Último recurso: `ssm "$EC2_A" "bash /opt/nodo-ruta/repo/despliegue/aws/iniciar.sh"`, que recarga los 6 pedidos sintéticos de la semilla porque `cargar-inicial.sql` solo actúa si falta la tabla (recrea además los contenedores de A).

## AWS07 - Destrucción y verificación de que no queda nada

**Objetivo.** Dejar la cuenta sin costo. **Orden estricto: 04 (front, si existe), 03, luego 02 (vaciando antes el bucket con todas sus versiones), luego 01**, porque una pila no se borra mientras otra importa sus exports. El parámetro de SSM no pertenece a ninguna pila y se borra aparte. Esta prueba **es destructiva**: hazla solo cuando AWS04 a AWS06 estén registradas (los respaldos de S3 se pierden). Requiere el bloque 0 (variables, `BUCKET`); la parte del front usa también `salida`.

**Primero el front (si se desplegó la pila `nodo-ruta-front`, D16).** El bucket del front debe vaciarse antes (una pila no borra un bucket con objetos) y la pila del front debe borrarse **antes** que la de cómputo, porque importa su salida `DnsAlb`. Borrar la distribución tarda varios minutos (CloudFormation la deshabilita y luego la elimina).

```bash
P=evidencias/AWS07_destruccion
BF=$(salida nodo-ruta-front NombreBucket)
echo "$(marca) vaciar bucket del front $BF" | tee "$P".txt
aws s3 rm "s3://$BF" --recursive | tee -a "$P".txt
echo "$(marca) borrar nodo-ruta-front" | tee -a "$P".txt
aws cloudformation delete-stack --stack-name nodo-ruta-front
aws cloudformation wait stack-delete-complete --stack-name nodo-ruta-front
echo "$(marca) front borrada" | tee -a "$P".txt
```

Si solo quieres **revertir las reglas de D16 sin destruir el cómputo** (con `nodo-ruta-front` ya borrada, porque importa `DnsAlb`): actualiza `nodo-ruta-computo` con la plantilla anterior (sin `ClaveOrigen` ni `CidrAcceso`) y luego `nodo-ruta-red` con la anterior (sin la prefix list). Los parámetros que ya no existen no se pasan:

```bash
git show feat/infra-computo:infra/aws/03-computo.yaml > "$TMPDIR/03-computo-anterior.yaml"
git show feat/infra-computo:infra/aws/01-red.yaml > "$TMPDIR/01-red-anterior.yaml"
aws cloudformation update-stack --stack-name nodo-ruta-computo --template-body "file://$TMPDIR/03-computo-anterior.yaml" --capabilities CAPABILITY_IAM --parameters ParameterKey=PilaRed,UsePreviousValue=true ParameterKey=PilaDatos,UsePreviousValue=true ParameterKey=VersionGit,UsePreviousValue=true ParameterKey=UrlRepo,UsePreviousValue=true ParameterKey=TipoInstancia,UsePreviousValue=true ParameterKey=AmiX86,UsePreviousValue=true ParameterKey=AmiArm,UsePreviousValue=true
aws cloudformation wait stack-update-complete --stack-name nodo-ruta-computo
aws cloudformation update-stack --stack-name nodo-ruta-red --template-body "file://$TMPDIR/01-red-anterior.yaml" --parameters ParameterKey=CidrAcceso,UsePreviousValue=true ParameterKey=CidrVpc,UsePreviousValue=true
aws cloudformation wait stack-update-complete --stack-name nodo-ruta-red
```

Luego, en la destrucción total:

```bash
P=evidencias/AWS07_destruccion
echo "$(marca) borrar nodo-ruta-computo" | tee -a "$P".txt
aws cloudformation delete-stack --stack-name nodo-ruta-computo
aws cloudformation wait stack-delete-complete --stack-name nodo-ruta-computo
echo "$(marca) computo borrada" | tee -a "$P".txt
```

Vaciar el bucket (objetos, versiones y marcas de borrado). Si no hay nada, no imprime nada:

```bash
P=evidencias/AWS07_destruccion
vaciar() { aws s3api list-object-versions --bucket "$BUCKET" --query "${1}[].[Key,VersionId]" --output text | while read -r k v; do [ -n "$v" ] || continue; aws s3api delete-object --bucket "$BUCKET" --key "$k" --version-id "$v" > /dev/null; echo "borrado $k"; done; }
vaciar Versions | tee -a "$P".txt
vaciar DeleteMarkers | tee -a "$P".txt
aws s3api list-object-versions --bucket "$BUCKET" --query "length([Versions,DeleteMarkers][])" --output text | tee -a "$P".txt
```

El último número debe ser `0` (o `None`). Después la pila de datos (RDS tarda unos minutos en borrarse), el parámetro y la red:

```bash
P=evidencias/AWS07_destruccion
echo "$(marca) borrar nodo-ruta-datos" | tee -a "$P".txt
aws cloudformation delete-stack --stack-name nodo-ruta-datos
aws cloudformation wait stack-delete-complete --stack-name nodo-ruta-datos
echo "$(marca) datos borrada" | tee -a "$P".txt
aws ssm delete-parameter --name /nodo-ruta/db/password | tee -a "$P".txt
echo "$(marca) borrar nodo-ruta-red" | tee -a "$P".txt
aws cloudformation delete-stack --stack-name nodo-ruta-red
aws cloudformation wait stack-delete-complete --stack-name nodo-ruta-red
echo "$(marca) red borrada" | tee -a "$P".txt
```

Si el borrado de la red falla por interfaces de red (ENI) que el ALB aún no soltó, espera 2 a 5 minutos y repite el `delete-stack`.

**Verificación final.** La primera consulta lista todo lo que aún lleve la etiqueta `proyecto=nodo-ruta`; las demás comprueban por servicio (la API de etiquetas puede tardar unos minutos en reflejar los borrados, y no ve recursos sin etiqueta):

```bash
P=evidencias/AWS07_destruccion
echo "$(marca) verificacion final" | tee -a "$P".txt
aws resourcegroupstaggingapi get-resources --tag-filters Key=proyecto,Values=nodo-ruta --query "ResourceTagMappingList[].ResourceARN" --output text | tee -a "$P".txt
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE ROLLBACK_COMPLETE DELETE_FAILED --query "StackSummaries[?starts_with(StackName,'nodo-ruta')].StackName" --output text | tee -a "$P".txt
aws ec2 describe-instances --filters "Name=tag:proyecto,Values=nodo-ruta" "Name=instance-state-name,Values=pending,running,stopping,stopped" --query "Reservations[].Instances[].InstanceId" --output text | tee -a "$P".txt
aws elbv2 describe-load-balancers --query "LoadBalancers[?starts_with(LoadBalancerName,'nodo-')].LoadBalancerArn" --output text | tee -a "$P".txt
aws rds describe-db-instances --query "DBInstances[].DBInstanceIdentifier" --output text | tee -a "$P".txt
aws s3api head-bucket --bucket "$BUCKET" 2>&1 | tee -a "$P".txt
aws ssm get-parameter --name /nodo-ruta/db/password 2>&1 | tee -a "$P".txt
```

**CUMPLE si:** las pilas desaparecen sin `DELETE_FAILED`, las consultas por servicio salen vacías, `head-bucket` y `get-parameter` responden `404` / `ParameterNotFound`, y la consulta por etiqueta no devuelve nada. Quedan **a propósito** (no son de las pilas y no cuestan): la alerta de presupuesto, el proveedor OIDC de GitHub y el rol `github-actions-nodo-ruta`; si este rol lleva la etiqueta `proyecto=nodo-ruta` aparecerá en la consulta por etiqueta y no es un fallo.

## AWS08 - Interfaz y API por CloudFront (D16)

**Objetivo.** Comprobar que la interfaz se sirve por HTTPS desde S3 a través de CloudFront, que `/pedidos` y `/health` llegan al ALB por CloudFront (sin caché, alternando entre las dos instancias), y que el acceso directo al ALB desde la IP permitida sigue funcionando. Hazla **antes** de AWS07 (que destruye todo). Requiere haber hecho los pasos (a) a (e) de la sección "Pila del front" de [README.md](README.md) (red y cómputo actualizados, front creada y publicada).

**Qué se puede probar y qué no.** Una solicitud al ALB con un encabezado falso o desde otra IP **no se puede simular** desde tu equipo: el grupo de seguridad solo deja entrar a tu IP y a CloudFront, y tu IP entra siempre por la regla de IP del listener. Eso queda como **diseñado** (se verifica leyendo la configuración, abajo), igual que el rechazo de otras IP en la CloudFront Function (solo se puede ver el caso permitido). Lo probado será: 200 por CloudFront, redirección a HTTPS, sin caché en la API, y el ALB directo sin encabezado desde la IP permitida.

```bash
CF=$(salida nodo-ruta-front UrlFront)
ALB=$(salida nodo-ruta-computo UrlAlb)
LISTENER=$(aws elbv2 describe-listeners --load-balancer-arn $(salida nodo-ruta-computo ArnAlb) --query "Listeners[0].ListenerArn" --output text)
P=evidencias/AWS08_front_cloudfront
echo "$(marca) $CF" | tee "$P".txt
curl -s -o /dev/null -w "interfaz /: %{http_code} %{content_type}\n" "$CF/" | tee -a "$P".txt
curl -s "$CF/" | head -c 300 | tee -a "$P".txt
echo | tee -a "$P".txt
curl -s -o /dev/null -w "http -> https en /health: %{http_code} %{redirect_url}\n" "http://${CF#https://}/health" | tee -a "$P".txt
curl -s -o /dev/null -w "/pedidos por CloudFront: %{http_code} %{content_type}\n" "$CF/pedidos" | tee -a "$P".txt
for i in 1 2 3 4 5 6; do curl -s "$CF/health" | head -c 200 | tee -a "$P".txt; echo | tee -a "$P".txt; done
curl -sI "$CF/pedidos" | grep -i "^x-cache" | tee -a "$P".txt
curl -sI "$CF/assets/$(curl -s "$CF/" | grep -o 'index-[A-Za-z0-9_-]*\.js' | head -1)" | grep -i "^x-cache\|^cache-control" | tee -a "$P".txt
curl -s -o /dev/null -w "ALB directo /pedidos sin encabezado (IP permitida): %{http_code}\n" "$ALB/pedidos" | tee -a "$P".txt
aws elbv2 describe-listeners --listener-arns "$LISTENER" --query "Listeners[0].DefaultActions[0].[Type,FixedResponseConfig.StatusCode]" --output text | tee -a "$P".txt
aws elbv2 describe-rules --listener-arn "$LISTENER" --query "Rules[].[Priority,Conditions[0].Field]" --output text | tee -a "$P".txt
```

(El resumen de reglas no imprime el valor del encabezado: así la clave no queda en la evidencia.) Abre también `$CF` en el navegador, desde tu IP: debe cargar la interfaz con los 6 pedidos y el estado.

**CUMPLE (criterio nuestro [S]) si:** (1) `/` da 200 con `text/html` y el cuerpo empieza con el HTML de la interfaz; (2) `http://` redirige (301) a `https://`; (3) `/pedidos` y `/health` dan 200 por CloudFront, con `instancia` alternando entre las dos zonas en las 6 consultas; (4) la API sale con `Miss from cloudfront` (sin caché) y el `.js` de `assets/` con `cache-control: public,max-age=31536000,immutable` (y `Hit` en una segunda consulta); (5) el ALB directo desde tu IP da 200 sin encabezado; (6) el listener tiene acción por defecto `fixed-response 403` y las reglas de prioridad 1 (`http-header`) y 2 (`source-ip`). **Diseñado, no probado:** rechazo de otras IP en el ALB (grupo de seguridad), 403 por encabezado falso o ausente desde una IP de CloudFront, y 403 de la CloudFront Function para IP ajenas. Anótalo así en `EVIDENCIAS.md`. Si la creación de la distribución falló por la política de la organización, ese es el resultado (AWS08 = NO CUMPLE) y se reporta con el error real.

## Qué falta registrar

Tras cada prueba, añade su ficha (AWS04 a AWS08) a `EVIDENCIAS.md` con el formato de AWS01 a AWS03 (qué queremos comprobar, pasos, resultado observado con los números medidos, CUMPLE o no, ruta de la evidencia) y confirma en `docs/` qué es **probado** y qué sigue **solo diseñado**.
