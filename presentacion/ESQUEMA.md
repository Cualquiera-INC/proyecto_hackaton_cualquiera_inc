# Esquema compartido del pitch de 3 minutos (fuente única para las slides y el guion)

Decisión del equipo (28-11-2026): el pitch dura **3:00** y tiene **4 slides**, sin video y sin slides de respaldo. La versión larga (13 slides) queda en el historial de git (commit 6282709).
Reglas: cada número sale de EVIDENCIAS.md con su ID; nunca escribir la expresión "alta disponibilidad" (decir "tolerancia a la caída de un servidor"); distinguir probado de diseñado; poco texto en pantalla.

## Identidad visual (igual que antes)
Estud-IA (assets/logo-estudia.png, transparente), paleta azul noche + naranja/magenta/verde lima/cian/violeta, onda de partículas, motivo Villa Nube (nubes, pueblo sobre las nubes), íconos oficiales AWS en assets/aws-icons/, logos Nodo Ruta y Alcaldía de Medellín.

## Enlace del QR
URL en vivo (despliegue público del 28-11-2026, D18): https://d2t4p68czj96l8.cloudfront.net
Ojo: cambia en cada despliegue nuevo desde cero. El HTML debe tener la URL en UN solo lugar (constante al inicio del script) y aceptar ?url=... para sobrescribirla sin editar el archivo.

## Slides
| # | Título | Qué se ve | Tiempo |
|---|---|---|---|
| 1 | Hook + problema | Pregunta de apertura grande: "¿Qué pasa si el único servidor se apaga a mitad del día?". Debajo, en una línea: Nodo Ruta (ficticia) consulta sus entregas en UNA instancia, con los datos adentro y cambios a mano → si cae, operaciones queda a ciegas y nadie sabe cuánto tarda en volver. Tres chips de actores: Operaciones · Responsable técnico · Coordinación logística. QR pequeño a la app en vivo (el mismo de la slide 4). Logos Estud-IA y Nodo Ruta. | 0:30 |
| 2 | La solución | Diagrama AWS animado con íconos: Usuario → CloudFront (HTTPS) → S3 front / ALB → EC2 A (us-east-2a) y EC2 B (us-east-2b) → RDS PostgreSQL (subred privada) ; S3 respaldos (pg_dump + SHA-256) ; GitHub Actions → OIDC → CloudFormation (4 pilas). Franja inferior: "Todo es código: un botón crea (~16 min, AWS09) y otro destruye (8 min 28 s, AWS10)". | 0:45 |
| 3 | La prueba (medido, no estimado) | Protagonista: línea de tiempo AWS04 (se apaga EC2 B → 5 errores de 299 (1,7 %) entre 2,1 y 9,8 s → 0 errores → vuelve sola a los 40,6 s). Abajo 3 cifras: AWS06b restauración desde S3 en 8,6 s · I07 0 errores en 708 consultas al actualizar · I05c 157 ms restaurando datos en local. Una línea honesta: "Límite: la base en AWS es una sola (RDS Single-AZ, D13)". | 1:05 |
| 4 | Pruébenlo + cierre | QR grande a la URL en vivo, con la URL escrita debajo; "Escaneen: está en vivo ahora, en dos zonas de AWS". Frase de cierre: "Tolera la caída de un servidor. Datos que se verifican. Tiempos medidos." "Gracias · Preguntas". Logos Estud-IA, Nodo Ruta, Alcaldía. | 0:40 |
Total: 3:00. Quién habla: [asignar].

## Archivo único para enviar
`python scripts/empaquetar_pitch.py` genera `presentacion/index.html`: la presentación con todas las imágenes incrustadas (~330 KB), que se abre sola, sin la carpeta `assets/` y sin internet. Regenerarlo después de cada cambio en `pitch.html`.
