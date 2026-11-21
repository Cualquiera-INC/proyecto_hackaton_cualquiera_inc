# Registro del equipo
Equipo: [completar]
Integrantes y responsabilidades: [completar — responsable de despliegue, de pruebas y de documentación]
Fecha: 21 de noviembre de 2026
Modalidad: local con contenedores (Docker Desktop en Windows 11). El despliegue en nube queda como diseño pendiente.

Arquitectura elegida y motivo:
- Un proxy inverso NGINX 1.28-alpine publicado solo en 127.0.0.1:8080 como punto de acceso común.
- Dos instancias de la aplicación (app1 y app2) construidas desde el mismo Dockerfile, en la red interna `nodo-ruta-lab_default`, sin puertos publicados en el host.
- Los datos están en `data/pedidos.json`, fuera de los contenedores. Se montan con bind mount en solo lectura en ambas instancias.
- Respaldos en `respaldos/`, con huella SHA-256 generada por `scripts/datos.py`.
- Observación:
  - Healthcheck de Compose contra `/health` cada 5 s.
  - Log de acceso de NGINX que incluye `upstream=` y `upstream_status=`.
  - Campo `instancia` en cada respuesta.
  - Script `verificar_servicio.py` para guardar evidencias en JSON.
- Motivo: es el MVP mínimo que separa la aplicación de sus datos, reparte las solicitudes entre dos instancias, permite ver qué instancia responde y deja recuperar los datos desde un respaldo verificado.

Ayudas utilizadas y cambios realizados: se usó la ayuda opcional (`ayuda_opcional/compose.yaml` y `nginx.conf`) sin modificaciones. [completar si el equipo hace cambios propios]

Recursos, permisos y posibles costos:
- Ejecución local: no se contrataron recursos y no hubo costos.
- Solo se expone 127.0.0.1:8080. Las aplicaciones no publican puertos y el contenedor corre con un usuario sin privilegios (UID 10001). No hay secretos en la imagen.
- Factores de costo en un despliegue en nube (sin precios):
  - horas de cómputo de cada instancia;
  - balanceador de carga;
  - almacenamiento de datos y respaldos;
  - transferencia de datos de salida;
  - retención de registros;
  - registro de imágenes de contenedor.

# Fichas de prueba

## I01 — Consulta por el acceso común
Qué queremos comprobar: que el punto de acceso común reparte las consultas entre app1 y app2.
Versión y estado inicial: `datos-v1`; app1 y app2 en estado healthy; proxy iniciado.
Pasos para repetirla:
```
python scripts/datos.py preparar
docker compose -f ayuda_opcional/compose.yaml up -d --build
docker compose -f ayuda_opcional/compose.yaml ps
python scripts/verificar_servicio.py --esperadas app1,app2 --salida evidencias/inicio.json
```
Resultado esperado: 10 respuestas HTTP 200 de las dos instancias.
Resultado observado: 10 de 10 respuestas HTTP 200, de app1 y de app2, con versión `datos-v1`. El log del proxy muestra que `upstream=` alterna entre 172.19.0.2 y 172.19.0.3 (round-robin). La respuesta más lenta tardó 32 ms.
Inicio, fin y duración: 08:21:01 (13:21:01 UTC), duración inferior a 1 s.
Archivo de evidencia: `evidencias/inicio.json`
¿Cumple? Sí
Error encontrado y ajuste: ninguno.
Resultado al repetir la prueba: [completar en I06]

## I02 — Detención de app1
Qué queremos comprobar: que el servicio sigue respondiendo a través de app2 cuando app1 se detiene.
Versión y estado inicial: `datos-v1`; las dos instancias en estado healthy.
Pasos para repetirla:
```
docker compose -f ayuda_opcional/compose.yaml stop app1
python scripts/verificar_servicio.py --esperadas app2 --salida evidencias/fallo_app1.json
```
Resultado esperado: todas las respuestas vienen de app2, aunque puede haber errores breves.
Resultado observado:
- 10 de 10 respuestas HTTP 200, todas de app2. El usuario no vio ningún error.
- Una consulta tardó unos 1016 ms, frente a menos de 35 ms en el resto. Corresponde al `proxy_connect_timeout 1s`: NGINX intentó conectar con app1, que estaba detenida, y reintentó en app2 (`proxy_next_upstream`).
- Es una detección pasiva: NGINX no consulta `/health`.

Inicio, fin y duración: app1 se detuvo hacia las 08:21:13. La primera consulta servida por app2 fue a las 08:21:26. La interrupción visible para el usuario fue de 0 errores, con una latencia de unos 1 s en una consulta.
Archivo de evidencia: `evidencias/fallo_app1.json`
¿Cumple? Sí
Error encontrado y ajuste: no hubo errores. La latencia de 1 s se podría reducir con un health check activo o con un `proxy_connect_timeout` menor.
Resultado al repetir la prueba: [completar en I06]

## I03 — Recuperación de app1
Qué queremos comprobar: que app1 vuelve al servicio después de reiniciarse.
Versión y estado inicial: `datos-v1`; app1 detenida y app2 healthy.
Pasos para repetirla:
```
docker compose -f ayuda_opcional/compose.yaml start app1
docker compose -f ayuda_opcional/compose.yaml ps
python scripts/verificar_servicio.py --esperadas app1,app2 --salida evidencias/recuperacion_app1.json
```
Resultado esperado: vuelven a responder app1 y app2.
Resultado observado: app1 pasó a healthy unos 6 s después del `start`. Hubo 10 de 10 respuestas HTTP 200 de app1 y de app2.
Inicio, fin y duración: verificación a las 08:21:51. Recuperación de app1 en unos 6 s, según `ps`.
Archivo de evidencia: `evidencias/recuperacion_app1.json`
¿Cumple? Sí
Error encontrado y ajuste: ninguno. La recuperación fue manual (`start`). Docker no reinicia por sí solo un contenedor marcado como unhealthy.
Resultado al repetir la prueba: [completar en I06]

## I04 — Recreación de un contenedor y persistencia de datos
Qué queremos comprobar: que los datos están fuera del almacenamiento efímero y sobreviven a la recreación del contenedor.
Versión y estado inicial: `datos-v1`; las dos instancias en estado healthy.
Pasos para repetirla:
```
docker compose -f ayuda_opcional/compose.yaml up -d --force-recreate app1
python scripts/verificar_servicio.py --esperadas app1,app2 --salida evidencias/recreacion.json
```
Resultado esperado: el nuevo contenedor de app1 responde con la misma versión de datos.
Resultado observado: 10 de 10 respuestas HTTP 200, de app1 y de app2, con `datos-v1`. El contenedor se recreó en unos 3,5 s.
Inicio, fin y duración: verificación a las 08:22:08.
Archivo de evidencia: `evidencias/recreacion.json`
¿Cumple? Sí
Error encontrado y ajuste: ninguno. Esta prueba demuestra persistencia, pero no sirve como respaldo.
Resultado al repetir la prueba: [completar en I06]

## I05 — Respaldo, alteración y restauración de datos
Qué queremos comprobar: que un fallo en los datos compartidos afecta a las dos instancias y que se recupera desde un respaldo verificado.
Versión y estado inicial: `datos-v1` con 6 pedidos (PED-001 a PED-006); las dos instancias en estado healthy.
Pasos para repetirla:
```
python scripts/datos.py respaldar
python scripts/datos.py simular-error
python scripts/verificar_servicio.py --salida evidencias/datos_corruptos.json
python scripts/datos.py restaurar --respaldo respaldos/20261121_082215_066863.json
python scripts/verificar_servicio.py --esperadas app1,app2 --salida evidencias/restauracion.json
```
Resultado esperado:
- Con los datos alterados, ninguna instancia responde 200.
- Después de restaurar, se obtiene 200 con `datos-v1` y los 6 pedidos.

Resultado observado:
- Respaldo creado: `respaldos/20261121_082215_066863.json`, con su archivo `.sha256`.
- Con los datos corruptos:
  - La primera consulta recibió **503**. NGINX probó app2 y app1 (`upstream_status=503, 503`).
  - Por `max_fails=1 fail_timeout=5s`, NGINX marcó las dos instancias como caídas.
  - Las otras 9 consultas recibieron **502** ("no live upstreams") sin llegar a las aplicaciones.
  - Conclusión: la segunda instancia no protege ante un fallo de datos compartidos.
- Después de restaurar:
  - Se obtuvieron 10 de 10 respuestas HTTP 200, de app1 y de app2.
  - En `/pedidos` se comprobó en el navegador la versión `datos-v1` y los 6 pedidos con los mismos estados que el original.
  - La huella SHA-256 se validó antes de escribir los datos.

Inicio, fin y duración:
- Error detectado: 08:22:28 (13:22:28 UTC).
- Servicio verificado: 08:24:11 (13:24:11 UTC).
- **Tiempo de recuperación: 1 min 43 s.** Casi todo ese tiempo fue la ejecución manual de comandos; la escritura de la restauración tarda menos de 1 s.

Archivos de evidencia:
- `evidencias/datos_corruptos.json`
- `evidencias/restauracion.json`
- log del proxy: `docker compose -f ayuda_opcional/compose.yaml logs --tail 50 proxy`

¿Cumple? Sí. El fallo con los datos corruptos era el resultado esperado de la prueba.
Error encontrado y ajuste:
- El usuario ve un 502 del proxy en vez del 503 de la aplicación.
- La restauración es manual.
- Mejoras posibles: un script que automatice la restauración del último respaldo válido, y una escritura atómica (archivo temporal y luego reemplazo) para evitar el 503 breve durante la escritura.

Resultado al repetir la prueba: [completar en I06]

## I06 — Repetición por otro integrante
Qué queremos comprobar: que el procedimiento se puede reproducir siguiendo solo las instrucciones del equipo.
Versión y estado inicial: [completar]
Pasos para repetirla: los de la sección "Procedimiento para recrear y recuperar".
Resultado esperado: los mismos resultados de I01 a I05.
Resultado observado: [completar]
Inicio, fin y duración: [completar]
Archivo de evidencia: [completar — usar nombres nuevos, por ejemplo `evidencias/i06_inicio.json`]
¿Cumple? No realizado
Error encontrado y ajuste: [completar]
Resultado al repetir la prueba: [completar]

# Cierre
Qué funciona realmente (probado en local):
- Balanceo round-robin entre dos instancias detrás de un único punto de acceso.
- Conmutación a app2 cuando app1 se detiene, sin errores visibles; solo una consulta tardó unos 1 s.
- Recuperación de app1 y persistencia de los datos al recrear un contenedor.
- Respaldo con verificación de integridad SHA-256 y restauración comprobada por versión y contenido.
- Identificación de la instancia que responde (campo `instancia` y `upstream=` en el log de NGINX).

Qué quedó como propuesta o pendiente:
- Despliegue en nube: no hay una cuenta habilitada sin costo. [ajustar si el equipo tiene acceso]
- Prueba I06.
- Health check activo en el balanceador.
- Reinicio automático de instancias.
- Respaldos fuera del equipo.
- HTTPS.

Procedimiento para recrear y recuperar:
1. `python scripts/datos.py preparar` (solo la primera vez).
2. `docker compose -f ayuda_opcional/compose.yaml up -d --build` y esperar a que `ps` muestre las instancias como healthy.
3. Verificar con `python scripts/verificar_servicio.py --esperadas app1,app2 --salida evidencias/<nombre>.json`.
4. Si cae una instancia: `docker compose -f ayuda_opcional/compose.yaml start <app>`.
5. Si los datos están dañados (respuestas 502 o 503 en las dos instancias):
   - `python scripts/datos.py restaurar --respaldo respaldos/<archivo>.json`
   - verificar `/health` y `/pedidos`.
6. Para terminar: `docker compose -f ayuda_opcional/compose.yaml down`. Las carpetas `data/`, `respaldos/` y `evidencias/` se conservan.

Limitaciones:
- Dos contenedores en un mismo computador no son alta disponibilidad.
- Siguen siendo puntos únicos de fallo:
  - el computador;
  - el proxy NGINX (una sola instancia);
  - el archivo `data/pedidos.json`, compartido por las dos aplicaciones;
  - la carpeta de respaldos, que está en el mismo disco.
- NGINX solo detecta fallos de forma pasiva.
- El servidor HTTP de Python no está pensado para producción.

Cambios para el encuentro 3:
- Arquitectura en nube equivalente:
  - balanceador de carga administrado con HTTPS y health check activo contra `/health`;
  - dos o más instancias de contenedor en zonas de disponibilidad distintas, con reinicio automático;
  - datos en almacenamiento administrado (almacenamiento de objetos o base de datos);
  - respaldos versionados en otra ubicación;
  - registros centralizados;
  - permisos de mínimo privilegio para las instancias.
- Mejora priorizada: [completar — por ejemplo, health check activo y respaldos fuera del equipo]
