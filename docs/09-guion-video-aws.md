# 09 · Guion del video: Nodo Ruta en AWS

Guía paso a paso para levantar todo en AWS, grabar la demo (~5 min) y destruirlo. Los bloques se pegan tal cual en la terminal de macOS (zsh) desde la raíz del repo. No llevan líneas de comentario porque zsh las rompe.

## 0. Antes de empezar: tu IP con CIDR

El balanceador y CloudFront solo dejan entrar a **una IP**. Averigua la tuya:

```bash
MI_IP=$(curl -s https://checkip.amazonaws.com | tr -d '[:space:]'); echo "$MI_IP/32"
```

Lo que imprime, por ejemplo `181.132.209.220/32`, es tu **CIDR**:

- La IP es la dirección pública con la que sales a internet.
- El `/32` significa "solo esta IP exacta".

Si cambias de red (otra wifi, el celular, el lugar del pitch), la IP cambia y hay que volver a desplegar con la nueva. El paso 1 se puede repetir sin problema y solo actualiza lo necesario.

## 1. Levantar todo (fuera de cámara, ~30 min)

Elige **una** de las dos opciones.

### Opción A: desde GitHub Actions (recomendada; es la que se muestra en el video)

1. Ve a GitHub → **Actions** → **AWS Nodo Ruta** → **Run workflow**.
2. Llena el formulario:
   - **accion:** `desplegar`
   - **cidr:** tu IP con `/32`, la del paso 0
   - **version:** déjalo vacío
3. Dale **Run workflow** y espera ~30 min, hasta que salga ✅ verde.
4. Abre la ejecución. En el **resumen** al final está la URL `https://xxxx.cloudfront.net`.

Si falla, abre el paso "Ejecutar aws_nodo.py". El error dice qué recurso falló y por qué; si es un permiso (`AccessDenied`), nombra la acción que falta en la política del rol.

### Opción B: desde tu terminal

```bash
cd ~/Develop/estudIA/proyecto_hackaton_cualquiera_inc
git checkout main && git pull
python3 scripts/aws_nodo.py desplegar --evidencia AWS09
```

Sin `--cidr`, detecta tu IP solo. Al final imprime la URL de CloudFront.

### Comprobar que todo quedó arriba

```bash
cd ~/Develop/estudIA/proyecto_hackaton_cualquiera_inc
python3 scripts/aws_nodo.py estado
```

Deben verse:

- Las 4 pilas en `CREATE_COMPLETE` o `UPDATE_COMPLETE`.
- La URL de CloudFront.
- Los 2 destinos del balanceador en `healthy`.

## 2. Preparar la grabación

- Graba con **Cmd + Shift + 5** → "Grabar pantalla completa".
- Ten abiertas estas ventanas:
  - El navegador con la URL de CloudFront.
  - La consola de AWS en **Ohio (us-east-2)**.
  - GitHub Actions.
  - **Dos terminales** lado a lado, las dos en la carpeta del repo.
- En la **terminal 2**, pega esto antes de grabar. Prepara las variables de la escena 5:

```bash
cd ~/Develop/estudIA/proyecto_hackaton_cualquiera_inc
export AWS_DEFAULT_REGION=us-east-2
CF=$(aws cloudformation describe-stacks --stack-name nodo-ruta-front --query "Stacks[0].Outputs[?OutputKey=='UrlFront'].OutputValue" --output text)
EC2_B=$(aws cloudformation describe-stacks --stack-name nodo-ruta-computo --query "Stacks[0].Outputs[?OutputKey=='IdInstanciaB'].OutputValue" --output text)
echo "$CF  $EC2_B"
```

## 3. El guion (≈ 5 min)

### Escena 1: el despliegue automatizado (30 s), en GitHub Actions

Muestra la ejecución `desplegar` en verde y su resumen.

> "Toda la infraestructura está escrita como código en CloudFormation: red, base de datos, servidores, balanceador y CDN. Se despliega con un botón en GitHub Actions. GitHub entra a AWS por OIDC, sin claves guardadas, y con permisos limitados a los recursos del proyecto. Los secretos viven en AWS, nunca en el repo."

### Escena 2: la aplicación (45 s), en el navegador

1. Abre la URL de CloudFront y señala el **candado HTTPS**.
2. Muestra los **6 pedidos** y el estado del servicio.
3. Recarga varias veces: el campo **instancia** cambia entre `us-east-2a` y `us-east-2b`.

> "La interfaz se sirve desde S3 a través de CloudFront. Las consultas van al balanceador, que reparte entre dos servidores en dos zonas de disponibilidad. Los datos vienen de PostgreSQL en RDS."

### Escena 3: la infraestructura real (45 s), en la consola de AWS (Ohio)

1. **CloudFormation:** las 4 pilas `nodo-ruta-red`, `-datos`, `-computo` y `-front`.
2. **EC2 → Grupos de destino:** los 2 destinos en `healthy`.
3. **RDS:** la base `nodo-ruta-datos-pg`.
4. **S3:** el bucket del front y el de respaldos.

### Escena 4: el estado en un comando (20 s), en la terminal 1

```bash
python3 scripts/aws_nodo.py estado
```

### Escena 5: caída de un servidor en vivo (1 min 30 s), en las dos terminales

**Terminal 1:** monitor. Imprime la hora, qué servidor respondió y el código HTTP:

```bash
CF=$(aws cloudformation describe-stacks --region us-east-2 --stack-name nodo-ruta-front --query "Stacks[0].Outputs[?OutputKey=='UrlFront'].OutputValue" --output text); while true; do printf "%s " "$(date +%T)"; curl -s -4 -m 3 -w " HTTP %{http_code}" "$CF/health" | grep -o '"instancia": "[^"]*"\|HTTP [0-9]*' | tr '\n' ' '; echo; sleep 0.5; done
```

**Terminal 2:** apaga el servidor B:

```bash
aws ec2 stop-instances --instance-ids "$EC2_B" --query "StoppingInstances[0].CurrentState.Name" --output text
```

Espera ~30 s mirando la terminal 1 y vuelve a prender el servidor B:

```bash
aws ec2 start-instances --instance-ids "$EC2_B" --query "StartingInstances[0].CurrentState.Name" --output text
```

Espera ~45 s hasta que `us-east-2b` vuelva a aparecer y detén el monitor con **Ctrl + C**.

> "Apago un servidor. Durante unos 8 segundos algunas solicitudes fallan (502), hasta que el balanceador lo detecta con su health check y manda todo al otro. Lo medimos: 5 errores de 299 solicitudes, y cero después. Al prenderlo, vuelve solo en unos 40 segundos, sin tocar nada. Es tolerancia a la caída de una instancia, no alta disponibilidad: la base de datos sigue siendo un punto único de falla."

### Escena 6: respaldo a S3 (45 s), en la terminal 1

```bash
python3 scripts/aws_nodo.py probar
```

> "El respaldo sale de RDS, se guarda en S3 fuera de los servidores y de la base, y se comprueba su integridad con SHA-256. Ya ensayamos la restauración: el servicio volvió en 8,6 segundos (evidencia AWS06b). El primer intento falló por un error del script, y lo dejamos registrado tal cual."

**Opcional:** la restauración en vivo está en `infra/aws/PRUEBAS.md`, secciones **0**, **AWS05** y **AWS06**.

### Escena 7: cierre y destrucción (30 s), en GitHub Actions

1. **Run workflow** con:
   - **accion:** `destruir`
   - **confirmacion:** `destruir`
2. Muestra que arrancó. Tarda ~10 min; no hace falta grabarlo entero.

> "Igual que se crea, se destruye con un botón, en orden y verificando que no quede nada cobrando."

## 4. Después de grabar

- **Si no destruiste en la escena 7:** destruye ahora. Puede ser desde Actions (`destruir`) o con `python3 scripts/aws_nodo.py destruir`.
- **Comprueba que no queda nada:**

```bash
python3 scripts/aws_nodo.py estado
```

Debe decir 0 recursos del proyecto.

## Problemas típicos

| Síntoma | Causa | Arreglo |
|---|---|---|
| La página o `curl` dan **403** | Cambió tu IP | Repetir el paso 1 con la IP nueva |
| `EC2_B` sale vacío | La terminal 2 no tiene las variables | Pegar otra vez el bloque del paso 2 |
| El monitor solo muestra `2a` después de prender B | B sigue arrancando | Esperar hasta 1 min |
| Actions falla a mitad del despliegue | Un paso falló (se ve en "Ejecutar aws_nodo.py") | Corregir y lanzar `desplegar` otra vez con la misma IP: lo que ya existe no se toca |
| Actions falla con `AccessDenied` | Falta un permiso en la política del rol | Pasar el error; se agrega en `infra/aws/iam/politica-github-actions.json` |

**Costo:** mientras está arriba consume cerca de **USD 2 al día** de créditos. Destruir el mismo día.
