# Registro del equipo

Equipo: Cualquiera INC
Integrantes y responsabilidades: [completar — responsable de despliegue, de pruebas y de documentación]
Fecha: 21-11-2026 (primeras ejecuciones completas)
Modalidad: **contenedores locales** (Docker Desktop en Windows 11; repetido en Linux y en macOS). El despliegue en AWS está en preparación: ver [docs/02-arquitectura.md](docs/02-arquitectura.md).

Arquitectura elegida y motivo:
- NGINX publicado solo en `127.0.0.1:8080` como punto de acceso común.
- Dos instancias de la app (`app1`, `app2`) sin puertos publicados, que leen `data/pedidos.json` montado en solo lectura.
- Un contenedor `respaldo` que copia los datos cada 5 min a `respaldos/` con su huella SHA-256.
- Imágenes con versión y despliegue escalonado con rollback (`scripts/desplegar.py`).
- Motivo: es el MVP mínimo que separa la app de sus datos, reparte entre dos instancias, permite ver quién responde, recupera los datos desde un respaldo verificado y actualiza sin caída. Costo $0.

Ayudas utilizadas y cambios realizados:
- I01–I05 se corrieron sobre la ayuda opcional con `restart:` y el servicio `respaldo`; I06, sobre la ayuda opcional sin cambios.
- I07 e I08 usan el despliegue propio (`despliegue/`), que hoy es el **único stack oficial** e incluye el servicio de respaldo. Detalle de los cambios en [despliegue/README.md](despliegue/README.md).
- `app.py`: usa el hostname si falta `INSTANCE_ID`, responde `version_app` y se apaga de forma ordenada con SIGTERM.

Recursos, permisos y posibles costos: solo CPU, memoria y disco del computador. No hay cuentas de nube ni secretos. Solo se expone `127.0.0.1:8080`; las apps corren con un usuario sin privilegios (UID 10001). Los factores de costo en la nube están en [docs/04-seguridad-y-costos.md](docs/04-seguridad-y-costos.md).

# Fichas de prueba

Las evidencias están en `evidencias/` y el prefijo del archivo es el ID de la prueba. Las genera `scripts/verificar_servicio.py` (10 consultas secuenciales; no es una prueba de carga) o `scripts/monitorear.py` (consultas continuas). Horas en UTC salvo que se indique.

| ID | Prueba | Quién | Resultado |
|---|---|---|---|
| I01 | Acceso común y reparto | Oscar | Cumple |
| I02 / I02b | Caída de app1 (con registros) | Oscar | Cumple, 0 errores |
| I03 | Recuperación de app1 | Oscar | Cumple, ≈6 s |
| I04 | Recrear sin perder datos | Oscar | Cumple |
| I05 / I05c | Datos alterados → restaurar (RTO) | Oscar | Cumple, 157 ms |
| I05d | Elegir el punto de recuperación | Oscar | Cumple |
| I06 | Repetición por otro integrante | Steban | Parcial |
| I07 | Versión nueva sin caída + rollback manual | Steban | Cumple, 0 errores en 708 consultas |
| I07b | Despliegue sin caída con la interfaz en el proxy | Juan Pablo | Cumple, 0 errores en 233 consultas |
| I08 | Versión rota → rollback automático | Steban | Cumple (falta guardar evidencia) |
| — | Respaldo automático | Oscar | Cumple |

## I01 — Acceso común
Qué queremos comprobar: que el punto de acceso común responde y que se ven las dos instancias.
Versión y estado inicial: `datos-v1`, app1 y app2 healthy.
Resultado observado: 10/10 HTTP 200, con app1 y app2 alternando. **CUMPLE**. Evidencia: `evidencias/I01_inicio.json`

## I02 — Caída de app1
Pasos: `docker compose stop app1` (13:26:38) y consultar enseguida.
Resultado observado: 10/10 HTTP 200, todas atendidas por app2. **0 errores**. Una consulta tardó 1015 ms frente a 0–32 ms en las demás: es el `proxy_connect_timeout 1s` de NGINX antes de reintentar en app2 (detección pasiva). **CUMPLE**. Evidencia: `evidencias/I02_fallo_app1.json`

## I02b — Caída de app1 con registros
Qué queremos comprobar: relacionar cada consulta con su código HTTP y con la instancia que la atendió (la ficha pide "consultar sus registros").
Pasos: `docker compose stop app1` (13:43:39 UTC), `verificar_servicio.py`, y guardar `docker compose ps` y `docker compose logs --timestamps --tail 40 proxy app1 app2`.
Resultado observado: 10/10 HTTP 200 por app2. **CUMPLE**. El registro del proxy muestra el mecanismo:
```text
[error] upstream timed out ... while connecting to upstream ... upstream: "http://172.18.0.3:8080/pedidos"
"GET /pedidos HTTP/1.1" 200 upstream=172.18.0.3:8080, 172.18.0.4:8080 upstream_status=504, 200
```
NGINX intentó app1 (172.18.0.3), agotó el tiempo de conexión de 1 s y reintentó en app2 (172.18.0.4). El usuario recibió 200, con un segundo de demora. Evidencias: `evidencias/I02b_registros.txt` (incluye las IP de cada instancia), `I02b_antes.json` e `I02b_fallo_app1.json`

## I03 — Recuperación de app1
Pasos: `docker compose start app1` (13:26:43). Healthy a las 13:26:49 (**≈6 s**).
Resultado observado: 10/10 HTTP 200 con app1 y app2. **CUMPLE**. Evidencia: `evidencias/I03_recupera_app1.json`

## I04 — Recrear un contenedor
Pasos: `docker compose up -d --force-recreate app1`.
Resultado observado: el SHA-256 de `data/pedidos.json` es igual antes y después (`24a32881…49af5`), con versión `datos-v1` y 10/10 HTTP 200 con ambas instancias. **CUMPLE**. Evidencia: `evidencias/I04_recrear_app1.json`
Nota: esto prueba persistencia, no respaldo.

## I05 — Alterar datos y restaurar
Pasos: `datos.py simular-error` (13:27:21), consultar, `datos.py restaurar --respaldo respaldos/20261121_132624_895735.json`.
Resultado observado:
- Con los datos alterados, 3/3 respuestas fueron HTTP 503 y **las dos instancias cayeron a la vez** (punto único de fallo).
- El servicio `respaldo` se negó a copiar el archivo corrupto ("No se realizó la operación: Expecting property name…").
- Tras restaurar, 10/10 HTTP 200 y el SHA-256 coincide con el del respaldo y con su `.sha256`.
- **Tiempo de recuperación: 5,97 s** desde la alteración hasta el primer `/health` 200. Incluye las 3 consultas que confirmaron el 503. No hizo falta reiniciar las apps porque releen el archivo en cada petición.

**CUMPLE**. Evidencias: `evidencias/I05a_datos_alterados.json` (resultado REVISAR, que es lo esperado) y `evidencias/I05b_restaurado.json`

## I05c — Tiempo de recuperación de la restauración
Qué queremos comprobar: el tiempo de la restauración sola, sin las consultas de diagnóstico que inflaron I05.
Pasos: `simular-error` (/health → 503) y luego `restaurar`, consultando `/health` cada 50 ms hasta obtener 200 con `datos-v1`.
Resultado observado: el comando `restaurar` tardó **110 ms** y el primer 200 correcto llegó a los **157 ms**. **CUMPLE**.
Hallazgo: la verificación inmediata (`I05c_restaurado.json`) vio solo app1. Mientras los datos estaban alterados, app2 devolvió 503 y NGINX la sacó de la rotación durante `fail_timeout=5s` (`max_fails=1`). Repetida a los 6 s (`I05c_restaurado_tras_5s.json`), aparecen app1 y app2. Es decir, **el servicio vuelve en ~0,2 s, pero el reparto entre las dos instancias tarda hasta 5 s más**. Evidencia: `evidencias/I05c_rto_restauracion.txt`

## I05d — Elegir el punto de recuperación
Qué queremos comprobar: que podemos volver a una versión concreta, no solo que el archivo abre (es la prueba opcional de la guía).
Pasos: se cambió la copia de trabajo a `datos-v2` (PED-003: Pendiente → Entregado), se respaldó y se comprobó que el servicio la publicaba. Después se restauró el respaldo de `datos-v1` (`respaldos/20261121_132624_895735.json`).
Resultado observado: el servicio pasó de `datos-v2`/Entregado a `datos-v1`/Pendiente con app1 y app2 en 200. El contenido es igual al `pedidos.json` original y el SHA-256 coincide con el respaldo elegido. El respaldo de v2 se conserva. **CUMPLE**. Evidencias: `evidencias/I05d_punto_recuperacion.txt`, `I05d_v2_publicada.json` y `I05d_vuelta_a_v1.json`

## Respaldo automático
Resultado observado: el servicio `respaldo` creó copias cada 5 min (13:26, 13:31, 13:36 y, tras reiniciar el stack, 13:43 UTC). Las 5 copias tienen la huella SHA-256 correcta. Con datos corruptos se negó a respaldar (ver I05). **CUMPLE**. Evidencia: `evidencias/respaldo_automatico.txt`
Hallazgo: los nombres de los respaldos del contenedor usan la hora UTC, pero `datos.py respaldar` ejecutado a mano en Windows usa la hora local (UTC-5). Por eso el orden por nombre no es cronológico: hay que elegir el respaldo por su `version`, no por el nombre.
Integración en `despliegue/` (21-11, macOS con OrbStack): primer despliegue `v1`, actualización a `v2` y rollback a `v1` correctos con el servicio `respaldo` corriendo al lado; creó `respaldos/20261121_150624_174384.json` con su `.sha256`. Verificado por consola, sin archivo en `evidencias/`.

## I06 — Repetición por otro integrante (parcial)
Qué queremos comprobar: que otra persona, en otro PC, obtiene los mismos resultados.
Qué se hizo: Steban repitió I01–I05 en su propio equipo (Windows 11) usando la ayuda opcional sin modificaciones, de forma independiente a la corrida de Oscar.
Resultado observado:
- I01: 10/10 HTTP 200 con app1 y app2 alternando (`upstream=` entre 172.19.0.2 y 172.19.0.3). Máximo 32 ms. Evidencia: `evidencias/I06_inicio.json`
- I02: 10/10 HTTP 200 por app2 y 0 errores. Una consulta tardó ~1016 ms por el `proxy_connect_timeout 1s`. Evidencia: `evidencias/I06_fallo_app1.json`
- I03: app1 healthy ~6 s después del `start`; 10/10 HTTP 200 con las dos. Evidencia: `evidencias/I06_recuperacion_app1.json`
- I04: recreación en ~3,5 s; 10/10 HTTP 200 con `datos-v1`. Evidencia: `evidencias/I06_recreacion.json`
- I05: con datos corruptos, la primera consulta recibió **503** (`upstream_status=503, 503`) y las otras 9 recibieron **502** ("no live upstreams"), porque NGINX marcó las dos instancias como caídas. Tras restaurar, 10/10 HTTP 200 con `datos-v1` y los 6 pedidos. Tiempo total **1 min 43 s**, casi todo de comandos manuales (la escritura tarda menos de 1 s). Evidencias: `evidencias/I06_datos_corruptos.json` e `I06_restauracion.json`

¿Cumple? **Parcial**: los resultados coinciden con los de Oscar, pero se siguió la guía del reto y no el README del equipo. Falta que alguien despliegue con `scripts/desplegar.py` siguiendo solo el [README](README.md).
Hallazgo: el usuario ve un 502 del proxy en lugar del 503 de la app (mismo hallazgo que I05c). Mejora prevista: no reintentar ante 503 en NGINX.

## I07 — Versión nueva sin caída y rollback manual
Qué queremos comprobar: que se puede publicar una versión nueva de la aplicación, y volver a la anterior, sin que las consultas dejen de responder. Es la parte del reto que dice *"cuando una actualización introduce un error, las consultas dejan de responder"*.
Versión y estado inicial: aplicación `v2`, datos `datos-v1`; app1, app2 y proxy healthy (`despliegue/compose.yaml`, puerto 8080).
Pasos (dos terminales):
```
# Terminal A
python scripts/monitorear.py --segundos 180 --salida evidencias/I07_despliegue_y_rollback.json
# Terminal B, mientras corre A
python scripts/desplegar.py desplegar --version v4
python scripts/desplegar.py rollback
# Al terminar B, Ctrl+C en A
```
Resultado observado:
- El monitor mostró, en orden: `{app1: v2, app2: v2}` → `{app1: v4, app2: v2}` → `{app1: v4, app2: v4}` → `{app1: v2, app2: v4}` → `{app1: v2, app2: v2}`.
- **708 consultas en 83,9 s, 0 errores** (resultado `SIN_CAIDA`).
- Latencia: mediana 16 ms, p95 32 ms y máximo 297 ms. El máximo corresponde al reintento de NGINX en la otra instancia mientras una se recreaba.
- Antes de pasar a la segunda instancia, el script comprobó en cada una: healthy, `version_app` correcta y tráfico recibido a través del proxy.
- Despliegue v2 → v4: 11,8 s. Rollback v4 → v2: 9,4 s.

**CUMPLE**. Evidencia: `evidencias/I07_despliegue_y_rollback.json`. El historial queda en `python scripts/desplegar.py estado`.
Errores encontrados y ajustes:
- En un primer intento el monitor terminó (60 s) antes de que empezara el despliegue (`evidencias/I07_intento_monitor_corto.json` solo registra v2). Se repitió con 180 s.
- Otro intento falló porque el laboratorio de la ayuda opcional ocupaba el puerto 8080. Ahora el script lo detecta antes de empezar.
- Repetida desde Linux (Alpine, Python 3.14, Compose v5.7, puerto 8082): correcta y con 0 errores. Esa repetición encontró que un despliegue lanzado justo después del inicial se cancelaba porque el healthcheck del proxy seguía en `starting`; se corrigió haciendo que la precondición espere hasta 30 s.

## I07b — Despliegue sin caída con la interfaz web en el proxy
Qué queremos comprobar: que integrar la interfaz web en el proxy no rompe el despliegue escalonado.
Entorno: macOS con OrbStack, 21-11-2026. Stack `despliegue/` con el proxy `nodo-ruta-proxy:1.0.0` (NGINX + interfaz).
Pasos: primer despliegue `v1-ui` y, con `monitorear.py --segundos 25` corriendo, `desplegar --version v2-ui`.
Resultado observado:
- Primer despliegue en 25 s, incluida la construcción de la interfaz dentro de Docker.
- `/` → 200 `text/html` (interfaz); `/health` y `/pedidos` → 200 JSON alternando app1/app2; `/proxy-health` → 200. Los archivos JS se sirven como `application/javascript`.
- Actualización v1-ui → v2-ui en 7,9 s: **233 consultas, 0 errores** (`SIN_CAIDA`); latencia máxima 20 ms.
- `verificar_servicio.py --esperadas app1,app2`: CUMPLE. La interfaz mostró «Servicio disponible», la instancia, `datos-v1` y los 6 pedidos.

**CUMPLE**. Evidencia: `evidencias/I07b_despliegue_con_interfaz.json`

## I08 — Versión rota y rollback automático
Qué queremos comprobar: que si la versión nueva no arranca, el despliegue se revierte solo y el servicio nunca deja de responder.
Versión y estado inicial: aplicación `v2` en app1 y app2, todo healthy.
Pasos:
1. Añadir temporalmente en `app.py`, debajo de `port = int(...)`, la línea `raise RuntimeError("BUG SIMULADO")`.
2. Con el monitor corriendo en otra terminal: `python scripts/desplegar.py desplegar --version v3-roto`
3. Quitar la línea de `app.py`.

Resultado observado:
- En Windows: app1 se reinició 2 veces al arrancar. El script lo detectó en unos 2 s, devolvió app1 a v2 y terminó con código 1, todo en **4,2 s**. El monitor registró 345 consultas con 0 errores y un máximo de 313 ms.
- En Linux: mismo comportamiento, con 0 errores.
- En las dos pruebas app2 no se tocó.

¿Cumple? Sí (prueba técnica). **Falta guardar la evidencia**: repetir con `--salida evidencias/I08_rollback_automatico.json`.

# Cierre

Qué funciona realmente (probado en local):
- Reparto entre dos instancias detrás de un único punto de acceso, y conmutación a app2 cuando app1 cae, sin errores visibles.
- Recuperación de app1 y persistencia de los datos al recrear un contenedor.
- Respaldo automático cada 5 min y restauración verificada con SHA-256 (≈0,2 s), incluida la elección del punto de recuperación.
- Identificación de la instancia y de la versión que responden (`instancia`, `version_app` y `upstream=` en el log de NGINX).
- Despliegue de versiones nuevas sin caída, rollback manual y rollback automático (también en Linux).
- Reinicio automático de contenedores caídos (`restart: unless-stopped`).

Qué quedó pendiente:
- Despliegue en AWS (plan gratuito): diseño en [docs/02-arquitectura.md](docs/02-arquitectura.md).
- I06 completa siguiendo el README del equipo y la evidencia de I08.
- NGINX sin reintento ante 503 (evita el 502 tras un fallo de datos) y otras mejoras medidas.
- Rotación de respaldos y respaldos fuera del computador.
- HTTPS y health check activo (llegan con el balanceador de AWS).

Procedimiento para recrear y recuperar: [README](README.md).

Limitaciones:
- Dos contenedores en un mismo computador no son alta disponibilidad: es tolerancia a la caída de una instancia.
- Siguen siendo puntos únicos de fallo: el computador, el proxy NGINX, el archivo `data/pedidos.json` compartido y la carpeta de respaldos en el mismo disco.
- NGINX libre solo detecta fallos de forma pasiva y, tras un incidente de datos, saca las instancias de la rotación hasta por 3 s (5 s en la ayuda opcional).
- El servidor HTTP de Python no está pensado para producción.
