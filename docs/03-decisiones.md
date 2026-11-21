# 03 · Decisiones técnicas

Formato corto: qué decidimos, por qué y qué descartamos. 🟢 aceptada · 🟡 propuesta · 🔴 descartada.

## D1 · Orquestación local con Docker Compose 🟢
Lo trae la ayuda del reto, el equipo lo conoce y funciona igual en macOS, Windows y Linux. Descartado: Kubernetes (excesivo para 2 instancias).

## D2 · NGINX como proxy inverso 🟢
Punto de acceso común con reparto por turnos y reintento en la otra instancia. Su limitación (solo detección pasiva) está documentada y se resuelve en AWS con el health check del ALB. Descartados: Traefik y HAProxy (no aportan nada para este alcance).

## D3 · Datos: el JSON del reto, montado en solo lectura 🟢
La app lee `data/pedidos.json` en cada consulta. Se monta la **carpeta** `data/` (no el archivo) para poder reemplazarlo de forma atómica. Es lo más simple que cumple "datos fuera del contenedor" sin tocar la app.

## D4 · Respaldo con `datos.py` + servicio automático cada 5 min 🟢
Copia y huella SHA-256 que se verifica antes de restaurar, y nunca respalda un archivo dañado. RPO ≤ 5 min. En AWS, S3 con historial de versiones. Pendiente: rotar los respaldos antiguos.

## D5 · Despliegue escalonado con imágenes versionadas 🟢
`scripts/desplegar.py` actualiza una instancia a la vez, verifica salud, versión y enrutamiento, y revierte solo si la nueva falla. Imágenes `nodo-ruta:<versión>`, nunca `latest`. Responde a "una actualización introduce un error y las consultas dejan de responder" (I07, I08).

## D6 · Cambios mínimos a `app.py` 🟢
Solo para observar y desplegar: `version_app`, apagado ordenado con SIGTERM y el hostname cuando falta `INSTANCE_ID`. Además, CORS (`Access-Control-Allow-Origin: *` y `OPTIONS`) para que la interfaz web pueda consultar la API. Nada de lógica de negocio nueva.

## D7 · Scripts en Python con solo la biblioteca estándar 🟢
El equipo usa macOS, Windows y Linux. Cada script se ejecuta directamente (`python scripts/x.py`) y no hace falta instalar nada.

## D8 · Nube: AWS (plan gratuito) con EC2 + ALB + S3 🟢
El equipo tiene una cuenta nueva con el plan gratuito. Es la traducción directa del diseño local y permite probar la caída de una máquina. Detalle en [02-arquitectura.md](02-arquitectura.md).
- 🔴 ECS Fargate + RDS Multi-AZ: más caro y no hace falta para 6 pedidos de solo lectura.
- 🔴 Azure Container Apps: la cuenta disponible es de AWS.
- 🔴 EKS: cobra el panel de control y es excesivo.

## D9 · Microservicios y base de datos → fase 2 🔴 (por ahora)
Se habían propuesto en el encuentro 1 (3 microservicios + PostgreSQL). Se descartaron al llegar el paquete:
- partir una app de 3 rutas no le aporta nada al cliente;
- obligaría a reescribir la app, lo que rompe la regla de cambios mínimos;
- en local la base de datos sería otro punto único de falla;
- no cabe en el tiempo de construcción.

**Se reconsideran si** los pedidos pasan a modificarse a cada rato desde muchos puntos. Ahí sí hace falta una base de datos.

## D10 · Observabilidad sin herramientas pesadas 🟢
`instancia` y `version_app` en cada respuesta, el log de NGINX con el upstream y el tiempo, los healthchecks y los scripts `verificar_servicio.py` y `monitorear.py` como evidencia. En AWS: CloudWatch Logs y las métricas del ALB. Descartados: Prometheus y Grafana (fuera de alcance).

## D11 · Interfaz web de solo lectura en React + Vite 🟢 (PR #5, Silvia)
Una interfaz para que operaciones consulte los pedidos y el estado sin leer JSON. Es solo lectura y no cambia la API. Su CI está en GitHub Actions. Integrada al stack oficial: la imagen del proxy (`despliegue/Dockerfile.proxy`) la construye dentro de Docker y la sirve en `/`. Por eso el JSON de bienvenida de la app (`/`) ya no se ve a través del proxy; la API sigue en `/pedidos` y `/health`. En AWS se serviría desde S3 detrás de CloudFront.

## Pendientes medidos (mejoras para el siguiente PR)

| Mejora | Por qué | Estado |
|---|---|---|
| Quitar `http_503` del reintento de NGINX | Con datos dañados el usuario ve 502 y las instancias quedan castigadas hasta 3 s | 🟡 medido en laboratorio |
| Fijar `python:3.12-slim` en el Dockerfile | `python:3-slim` hoy instala 3.15 | 🟡 |
| `server_tokens off` | No mostrar la versión de NGINX | 🟡 |
| Endurecer contenedores (`read_only`, `cap_drop`, `no-new-privileges`) | Menos privilegios | 🟡 |
