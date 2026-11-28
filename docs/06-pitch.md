# 06 · Pitch final: Nodo Ruta

> Versión del 28-11-2026 (pitch de 3 minutos, 4 slides). Cada número sale de [EVIDENCIAS.md](../EVIDENCIAS.md) y lleva su ID. Lo que no está medido se dice como tal. Quién habla en cada parte queda como [asignar] hasta que el equipo lo defina.

**Presentación y guion:** las slides están en [`presentacion/pitch.html`](../presentacion/pitch.html) y el guion para ensayar en [`presentacion/guion.html`](../presentacion/guion.html); se abren con doble clic y funcionan sin internet (salvo el QR, que apunta a la URL en vivo). El esquema común está en [`presentacion/ESQUEMA.md`](../presentacion/ESQUEMA.md).

## Duración

El pitch dura **3:00** y tiene **4 slides**, sin video y sin slides de respaldo (decisión del equipo del 28-11-2026; ver [ESQUEMA.md](../presentacion/ESQUEMA.md)). La versión larga (13 slides, 5 minutos) queda en el historial de git (commit 6282709). Ritmo: 140 a 150 palabras por minuto, unas 427 palabras en total (~142 por minuto). El ritmo real se mide con el cronómetro del guion.

| # | Sección | Tiempo | Palabras | Quién |
|---|---|---|---|---|
| 1 | Hook y problema | 0:30 | 72 | [asignar] |
| 2 | La solución | 0:45 | 105 | [asignar] |
| 3 | La prueba (medido, no estimado) | 1:05 | 160 | [asignar] |
| 4 | Pruébenlo + cierre | 0:40 | 90 | [asignar] |
| | **Total** | **3:00** | **427** | |

## Hook de apertura (primeros 5 a 8 segundos)

Escena ilustrativa, sin cifras ni hechos inventados del caso (Nodo Ruta es ficticia). Se elige uno:

- **Principal:** "Media mañana. Los camiones están en la calle y el único servidor se apaga. ¿Qué ve operaciones? Nada."
- **Alternativa A:** "Si hoy se apaga el único servidor de su empresa, ¿cuánto tardan en volver? En Nodo Ruta nadie lo sabía. Nosotros lo medimos."
- **Alternativa B:** "Levanten la mano si alguna vez un servicio se cayó y nadie sabía cuánto iba a tardar en volver. A Nodo Ruta le podía pasar. Hoy les mostramos cuánto tarda, con números."

Si se usa una alternativa, se sigue desde "Nodo Ruta, una empresa ficticia…".

## 1. Hook y problema (0:30)

**En pantalla:** Pregunta grande: "¿Qué pasa si el único servidor se apaga a mitad del día?" + una línea del problema + 3 chips (Operaciones · Responsable técnico · Coordinación logística) + logos Estud-IA y Nodo Ruta.

> Media mañana. Los camiones están en la calle y el único servidor se apaga. ¿Qué ve operaciones? Nada. Esto le podía pasar a Nodo Ruta, una empresa ficticia de distribución: consulta sus entregas en una sola instancia, con los datos adentro y los cambios a mano. Si cae, operaciones queda a ciegas y nadie sabe cuánto tarda en volver. Somos el equipo Cualquiera INC, y esto es lo que construimos y medimos.

Evidencia: Escena ilustrativa, sin cifras. El caso (Nodo Ruta) es ficticio..

## 2. La solución (0:45)

**En pantalla:** Diagrama AWS animado: Usuario → CloudFront (HTTPS) → S3 front / ALB → EC2 A (us-east-2a) y EC2 B (us-east-2b) → RDS PostgreSQL (subred privada); S3 respaldos (pg_dump + SHA-256); GitHub Actions → OIDC → CloudFormation (4 pilas). Franja: "un botón crea, otro destruye".

> Esta es la solución, en AWS, y todo es código. El visitante entra por CloudFront, con HTTPS. Detrás hay un balanceador y dos servidores en dos zonas distintas: us-east-2a y us-east-2b. Los datos viven aparte, en una base PostgreSQL administrada, y los respaldos van a S3 con una huella SHA-256 para verificarlos. Los servidores no tienen puerto SSH y la contraseña de la base no está en el repositorio. Todo se crea desde GitHub Actions, sin claves guardadas, con cuatro pilas de CloudFormation. Un botón crea, en unos 16 minutos; otro destruye, en 8 minutos con 28 segundos. Creamos para probar y destruimos al terminar.

Evidencia: AWS03 AWS05 AWS09 AWS10 D13 D17.

## 3. La prueba (medido, no estimado) (1:05)

**En pantalla:** Línea de tiempo AWS04 animada: se apaga EC2 B → 5 errores de 299 (1,7 %) entre 2,1 y 9,8 s → 0 errores → vuelve sola a los 40,6 s. Abajo 3 cifras: AWS06b 8,6 s · I07 0 errores en 708 consultas · I05c 157 ms. Línea de límite: la base en AWS es una sola (D13).

> Ahora, la prueba: medida, no estimada. Con el monitor corriendo, apagamos uno de los dos servidores. Hicimos 299 consultas. Hubo 5 errores, un 1,7 por ciento, entre 2,1 y 9,8 segundos después de la parada. Después, cero errores, y el servidor volvió solo a los 40,6 segundos, sin que nadie lo tocara. Esos errores existen porque el balanceador tarda en sacar al servidor caído, y lo decimos nosotros, antes de que lo pregunten. ¿Y los datos? Restauramos desde S3: la primera respuesta correcta llegó en 8,6 segundos. Y no salió a la primera: el primer intento falló por un defecto del script; lo descubrimos ensayando, lo corregimos y lo repetimos. Al actualizar la versión en local, 708 consultas sin un solo error. Y al restaurar datos alterados en local, 157 milisegundos. Cada cifra tiene su identificador en la bitácora. Un límite honesto: en AWS la base de datos es una sola, un punto único de falla. Multi-AZ es solo diseño.

Evidencia: AWS04 AWS06b I07 I05c D13.

## 4. Pruébenlo + cierre (0:40)

**En pantalla:** QR grande a la URL en vivo, con la URL escrita debajo: "Escaneen: está en vivo ahora, en dos zonas de AWS". Frase de cierre y "Gracias · Preguntas". Logos Estud-IA, Nodo Ruta y Alcaldía de Medellín.

> Pero no tienen que creernos: escaneen el código QR. Si no abre, la dirección está escrita debajo. No es un video ni una maqueta: es el mismo servicio de la prueba, en vivo ahora mismo, en dos zonas de AWS. Durante las preguntas, ábranla y recarguen: verán qué servidor los atiende. Y pídannos cualquier número: todos tienen su ID en la bitácora. Nos llevamos tres frases. Tolera la caída de un servidor. Datos que se verifican. Tiempos medidos. Una nube que se mide deja de ser una promesa. Gracias. Preguntas.

Evidencia: D18 EVIDENCIAS.md.

## Enlace del QR

URL en vivo (despliegue público del 28-11-2026, D18): https://d2t4p68czj96l8.cloudfront.net. Cambia en cada despliegue nuevo desde cero: se confirma antes de subir al escenario y, si cambió, se abre `pitch.html?url=NUEVA_URL`. Si el QR no abre, se dice la dirección en voz alta.

Importante: dos contenedores en un mismo computador dan **tolerancia a la caída de una instancia**, nada más. La caída de una máquina completa solo se pudo probar en AWS, y allí la base de datos es un punto único de falla (D13, Multi-AZ es solo diseño).

l

## Preguntas probables del jurado

| Pregunta | Respuesta corta | Evidencia |
|---|---|---|
| ¿Por qué no Multi-AZ? | El plan gratuito de RDS solo permite Single-AZ y la regla del reto es cero costos. La base es un punto único de falla y lo decimos | D13, `docs/03-decisiones.md` |
| ¿Por qué no ECS ni Kubernetes? | El reto premia un MVP medido; con 2 servicios, dos EC2 detrás de un ALB bastan. Kubernetes está fuera del alcance. Además la política de la organización limita las regiones y servicios | D13, D15, CLAUDE.md |
| ¿Qué pasa si cae la base? | En local, la caída del primario no produjo errores porque se lee la réplica; si caen ambas, el microservicio sirve su copia en memoria. En AWS no hay réplica: solo la copia en memoria cubre caídas cortas y no se promete el 0 errores | STG08, STG12, D13 |
| ¿Cuánto cuesta? | No lo medimos. Referencia de lista de unos USD 2 al día con todo encendido, sin verificar; se destruye al terminar y hay alerta de USD 5 al mes | `docs/09`, AWS10 |
| ¿Por qué 5 errores durante la caída? | El ALB no reintenta en otra instancia: hasta que su health check (2 × 5 s) saca a la EC2 caída, algunas consultas fallan. Todos los errores cayeron entre 2,1 y 9,8 s tras la parada; después 0 | AWS04 |
| ¿Cómo evitan que alguien entre directo al balanceador? | El ALB solo acepta la lista de prefijos de CloudFront; su listener responde 403 salvo con un encabezado secreto o desde la IP permitida. Es una mitigación, no un control fuerte; el rechazo de otras IP está diseñado, no probado | AWS08, D16 |
| ¿Cómo sabemos que el respaldo sirve? | Se verifica el SHA-256 y se lee el índice con `pg_restore --list`; AWS06b restauró y devolvió 6 pedidos | AWS05, AWS06b |
| ¿Qué falló y qué aprendieron? | AWS06 falló por un defecto del script de restauración; ensayar la restauración antes de necesitarla lo descubrió | AWS06, AWS06b |
| ¿Se puede repetir? | Sí: un comando o un botón en Actions, y destruir con otro | AWS09, AWS10 |
| ¿El servicio ya no se cae nunca? | No lo prometemos. Tolera la caída de una instancia (local) o de un servidor (AWS), con los errores medidos y con la base como punto único de falla en AWS | EVIDENCIAS.md, cierre |

## Frase para coordinación logística (público no técnico)

> "Si se cae uno de los dos servidores, las consultas siguen funcionando después de unos segundos con algunos errores. Si los datos se dañan, los recuperamos en segundos y verificamos que sean los correctos. Lo que no cubrimos hoy: la caída de la base de datos en la nube."

## Si preguntan por el cambio frente a la ficha

La ficha inicial proponía microservicios y PostgreSQL; se descartaron (D9) y se retomaron (D12) con 14 pruebas medidas (STG01–STG14). Más piezas que operar es el costo que reconocemos.
