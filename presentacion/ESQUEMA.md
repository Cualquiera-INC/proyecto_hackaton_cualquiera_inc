# Esquema compartido del pitch (fuente única para las slides y el guion)

Fuente del contenido: docs/06-pitch.md (mergeado). Todo número sale de EVIDENCIAS.md con su ID. Duración objetivo: 5 min.
Regla: nunca escribir la expresión "alta disponibilidad"; decir "tolerancia a la caída de una instancia" o "de un servidor". Distinguir probado de diseñado.

## Identidad visual
- Marca del programa Estud-IA (logo en assets/logo-estudia.png, franja de la ficha en assets/franja-estudia.png).
  Paleta tomada de la ficha del reto: fondo azul noche casi negro (#070B14 a #0B1220), naranja Estud-IA (#F07A22 aprox.), magenta (#C83CC8 aprox.), verde lima (#8CC63F aprox.), cian de la onda de partículas (#1AA8F0 aprox.), violeta de la línea (#6A3DF0 aprox.), con destellos rojo/ámbar desenfocados (bokeh) en los bordes.
  Motivo gráfico: onda de puntos/partículas (cian a violeta) y una línea curva cian/violeta como la de la ficha.
- Temática "Villa Nube": es el pueblo-en-la-nube del curso Estud-IA Nube Intermedio. Úsala como motivo VISUAL (nubes, silueta de un pueblo/ciudad sobre las nubes, capas en parallax), no como parte de la historia: el caso del pitch es Nodo Ruta.
- Logo de Nodo Ruta: assets/logo-nodo-ruta.png (cuadrado azul noche con "n" blanca). Logo Alcaldía de Medellín: assets/logo-alcaldia.png (pie de portada y cierre, discreto).
- Íconos oficiales de AWS (exportados de draw.io, SVG): assets/aws-icons/ — cloudfront, elastic_load_balancing, ec2, rds, s3, cloudformation, identity_and_access_management, systems_manager, cloudwatch_2, vpc, budgets, certificate_manager_3, shield, auto_scaling2.
- Diagrama oficial final: assets/aws-final.png.

## Slides (13 + 2 de respaldo; sin video)
| # | Título | Qué se ve | Tiempo | Sección del docs/06 |
|---|---|---|---|---|
| 1 | Portada: Nodo Ruta | "Que la consulta de entregas no se caiga" · Equipo Cualquiera INC · Reto 16 · Estud-IA Nube e infraestructura, Capa 2 · logos | 0:10 | — |
| 2 | El problema | Una sola instancia, datos dentro de la app, cambios a mano; animación: un servidor solo que se apaga y la consulta queda en blanco | 0:15 | 1 |
| 3 | Quién lo vive | 3 tarjetas: Operaciones (sufre la caída), Responsable técnico (opera la solución; quien más cambia), Coordinación logística (necesita estado y límites) | 0:20 | 1 |
| 4 | Qué necesitaba el negocio | "No cinco nueves": 1 que la caída de un servidor no se note, 2 datos correctos, 3 recuperación en tiempo conocido | 0:25 | 2 |
| 5 | La solución local | Diagrama animado: NGINX → app1/app2 → pedidos1/2 → PostgreSQL primario + réplica; respaldo pg_dump + SHA-256 | 0:20 | 3 |
| 6 | La solución en AWS | Diagrama animado con íconos AWS: Operaciones → CloudFront (HTTPS) → S3 front / ALB → EC2 A (us-east-2a) y EC2 B (us-east-2b) → RDS PostgreSQL Single-AZ; S3 respaldos; SSM; paquetes de luz viajando por las flechas | 0:35 | 3 |
| 7 | Todo es código | 4 pilas CloudFormation (red, datos, cómputo, front) + GitHub Actions con OIDC, sin claves; un botón para crear y otro para destruir. Desde cero ~16 min (AWS09), destruir 8 min 28 s (AWS10) | 0:20 | 3 |
| 8 | Caída de un servidor (AWS04) | Línea de tiempo animada: parada → 5 errores de 299 (1,7 %) entre 2,1 y 9,8 s → 0 errores → vuelve sola a los 40,6 s. Hace de demo: no se proyecta video | 0:35 | 4 |
| 9 | Los números | Contadores animados: I02 0 errores · I05c 157 ms · I07 0 errores en 708 · I08 rollback en 4,2 s · STG08 0 errores en 418 · AWS06b 8,6 s · AWS09 ~16 min · AWS10 8 min 28 s | 0:30 | 5 |
| 10 | Seguridad y costos | Íconos IAM, SSM, VPC, Budgets: OIDC sin claves, secretos en SSM, sin SSH, filtro por IP, topes de costo (solo máquinas micro), alerta USD 5/mes, destruir al terminar; costo ~USD 2/día como referencia NO medida | 0:30 | 6 |
| 11 | Límites honestos | RDS Single-AZ = punto único de falla; errores durante la caída; fallos registrados tal cual (AWS06, primer AWS09, falso positivo AWS10); solo diseño: Multi-AZ, dominio propio, alarmas, autoescalado | 0:40 | 7 |
| 12 | Probado vs. diseñado | Tabla visual verde/ámbar/rojo (de docs/07, sección final) | (se muestra rápido o se salta) | 7 |
| 13 | Cierre | Frase de cierre + próximos pasos + "Gracias · Preguntas" + logos | 0:20 | 8 |
| R1 | Respaldo: preguntas del jurado | Las 10 preguntas con respuesta corta y evidencia | — | Preguntas |
| R2 | Respaldo: diagrama oficial | assets/aws-final.png a pantalla completa con zoom | — | — |
Total hablado = 5:00 exactos (10+15+20+25+20+35+20+35+30+30+40+20 s). La slide 12 es opcional y no cuenta. El video de la demo (docs/09) queda como material opcional aparte; en el pitch no se proyecta. Quién habla: [asignar] en todas.
