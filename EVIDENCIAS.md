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

# Staging: microservicios + PostgreSQL

Stack `despliegue/` con PostgreSQL (integrado desde la rama `staging`): `postgres`, `pedidos1`/`pedidos2` (microservicio HTTP), `app1`/`app2`, `proxy` y `respaldo` (`pg_dump`). Diseño en [docs/08-postgres-y-microservicio-pedidos.md](docs/08-postgres-y-microservicio-pedidos.md).
Entorno: Windows 11 + Docker Desktop, 21-11-2026, puerto 8080. Las horas de esta sección son locales (UTC-5). Monitor: `monitorear.py`, una consulta a `/pedidos` cada 0,1 s.

| ID | Prueba | Quién | Resultado |
|---|---|---|---|
| STG01 | Actualización escalonada de las 4 instancias | Steban | Cumple, 0 errores en 487 consultas |
| STG02 | Versión rota de pedidos → rollback automático (1.ª versión) | Steban | Rollback correcto, **1 error (504)** → hallazgo |
| STG03 | Despliegue de la corrección (alias `pedidos`) | Steban | 1 error (504), atribuible al código anterior |
| STG04 | Versión rota de pedidos → rollback automático (corregido) | Steban | Cumple, 0 errores en 328 consultas |
| STG05 | Respaldo → daño → restauración | Steban | Cumple, restauración 0,6 s |
| STG06 | Reinicio de PostgreSQL | Steban | Cumple, 0 errores en 239 consultas |
| STG07 | Transición en caliente a primario + réplica | Steban | Cumple, 0 errores en 983 consultas |
| STG08 | Caída del primario (con réplica) | Steban | Cumple, 0 errores en 418 consultas |
| STG09 | Caída de ambas bases (lectura en la consulta) | Steban | **No cumple: 2 errores 504** → hallazgo |
| STG10 | Despliegue con refresco en segundo plano | Steban | **2 errores (504/502)** → hallazgo |
| STG11 | Dos despliegues seguidos (corregido) | Steban | Cumple, 0 errores en 625 consultas |
| STG12 | Caída de ambas bases (corregido) | Steban | Cumple, 0 errores en 505 consultas |
| STG13 | Daño en los datos con copia en memoria | Steban | Cumple: 503 (no se tapa); servicio de vuelta en 3,2 s |
| STG14 | Caída del primario (código final) | Steban | Cumple, 0 errores en 381 consultas |

## STG01 — Actualización escalonada
Pasos: primer despliegue `stg-v1`; con el monitor corriendo, `desplegar --version stg-v2`.
Resultado observado: el script actualizó pedidos1 → pedidos2 → app1 → app2 y comprobó en cada una: healthy, `version_app` y, en las apps, tráfico a través del proxy. Tardó **15,3 s**. **487 consultas, 0 errores**; mediana 16 ms, p95 32 ms, máximo 1047 ms. **CUMPLE**. Evidencia: `evidencias/STG01_despliegue_escalonado.json`

## STG02 — Versión rota del microservicio de pedidos (primera versión)
Pasos: `raise RuntimeError("BUG SIMULADO")` en `servicio_pedidos.py` y `desplegar --version stg-v3-roto`.
Resultado observado: pedidos1 se reinició al arrancar. El script lo detectó en 2 s, lo devolvió a `stg-v2` y terminó con código 1; pedidos2 y las apps no se tocaron. Pero hubo **1 error: HTTP 504** (3016 ms).
Causa (medida): las apps llamaban a `pedidos1` por nombre. Mientras se recreaba, el nombre no existía, y resolver un nombre inexistente en la red `internal` tardó **7,84 s** (`socket.getaddrinfo` dentro de app1). El `timeout` HTTP no cubre la resolución DNS y el proxy cortó a los 3 s.
Corrección: alias de red `pedidos` compartido por las dos réplicas; la app resuelve el alias y prueba cada IP. Evidencia: `evidencias/STG02_rollback_automatico_pedidos.json`

## STG03 — Despliegue de la corrección
Resultado observado: stg-v2 → stg-v4 en 12,6 s. 352 consultas y 1 error 504, a las 11:11:45, mientras se recreaba pedidos1. En ese momento app1 y app2 todavía corrían stg-v2, con el código anterior y el mismo fallo de STG02; es la última vez que puede ocurrir. Evidencia: `evidencias/STG03_despliegue_alias_pedidos.json`

## STG04 — Versión rota del microservicio de pedidos (corregido)
Pasos: los mismos de STG02, con todo en stg-v4 y `desplegar --version stg-v5-roto`.
Resultado observado: rollback automático de pedidos1 en 3 s, con código de salida 1. **328 consultas, 0 errores**; máximo 1031 ms. **CUMPLE**. Evidencia: `evidencias/STG04_rollback_automatico_pedidos.json`

## STG05 — Respaldo, daño y restauración
Pasos: `datos.py respaldar`, `datos.py simular-error` (DROP TABLE pedidos), consultar `/health` y `datos.py restaurar --respaldo respaldos/<archivo>.dump`.
Resultado observado: con la tabla borrada, `/health` → **503** `error_datos`. `restaurar` verificó el SHA-256 y restauró en una transacción en **0,6 s**. Después, `/health` → 200 con `datos-v1` y `verificar` → 6 pedidos. **CUMPLE**. Evidencia: `evidencias/STG05_respaldo_restauracion.txt`
Ajuste: los respaldos manuales usaban hora local y los automáticos UTC, igual que en el hallazgo del respaldo JSON. Ahora los dos usan UTC.

## STG06 — Reinicio de PostgreSQL
Pasos: con el monitor corriendo, `docker compose -f despliegue/compose.yaml restart postgres`.
Resultado observado: el reinicio tardó ~1 s. **239 consultas, 0 errores**, máximo 953 ms: el pool del servicio de pedidos descarta las conexiones muertas y reconecta. **CUMPLE**, con una salvedad: una caída más larga de la base dejaría sin servicio a todo (punto único de falla). Por eso se hicieron STG07–STG14. Evidencia: `evidencias/STG06_reinicio_postgres.json`

## STG07 — Transición en caliente a primario + réplica
Qué queremos comprobar: que el stack que ya estaba corriendo, con una sola base, pasa a primario + réplica sin reinicializar los datos y sin caída.
Pasos: `desplegar --version stg-v6` con el monitor corriendo. `desplegar.py` recrea primero el primario (nuevas reglas de acceso y `wal_keep_size`), crea la réplica (que se copia sola con `pg_basebackup`) y luego actualiza pedidos1, pedidos2, app1 y app2.
Resultado observado: primario healthy en 1,4 s; réplica en 1,5 s; `pg_stat_replication` = `streaming`; la réplica tiene los 6 pedidos y `pg_is_in_recovery() = true`. **983 consultas, 0 errores**. Máximo **2953 ms**, cerca del límite de 3 s del proxy: al recrearse el primario, pedidos todavía corría stg-v4, que apuntaba al nombre `postgres` (mismo problema de DNS que STG02). No se repite después de la transición. **CUMPLE**. Evidencia: `evidencias/STG07_transicion_a_replica.json`

## STG08 — Caída del primario
Pasos: `docker compose stop postgres` durante 25 s y `start`.
Resultado observado: `/health` siguió en `ok` con `origen_datos: base` (en vivo, desde la réplica). **418 consultas, 0 errores**, máximo 79 ms. **CUMPLE**. Evidencia: `evidencias/STG08_caida_primario.json`

## STG09 — Caída de ambas bases (primera versión de la copia en memoria)
Pasos: `docker compose stop postgres postgres-replica` durante ~25 s.
Resultado observado: **2 errores 504** y p95 de 2016 ms. La copia en memoria existía, pero cada consulta intentaba primero la base: esperaba la conexión (2 s) y además resolver `pg-lectura`, que con las dos bases detenidas no existe (~8 s, como en STG02).
Corrección: las consultas ya no tocan la base. Un hilo de fondo la lee cada 1 s y las consultas responden desde memoria. Evidencia: `evidencias/STG09_caida_ambas_bases.json`

## STG10 — Despliegue con refresco en segundo plano
Resultado observado: stg-v6 → stg-v7 correcto, pero con **2 errores en el proxy** (504 de 0,3 s y 502) justo al recrear app2, 1 s después de confirmar app1. NGINX todavía tenía app1 marcada como caída por su propia recreación (`max_fails=1`, `fail_timeout=3s`) y no tuvo a quién reintentar. No es de la base: es la capa de NGINX.
Corrección: `desplegar.py` espera 3,5 s (`TIEMPO_ASENTAR`) tras confirmar una app antes de tocar la siguiente. Evidencia: `evidencias/STG10_despliegue_refresco_fondo.json`

## STG11 — Dos despliegues seguidos (corregido)
Pasos: `desplegar --version stg-v8` y enseguida `--version stg-v9`, con un solo monitor de 75 s.
Resultado observado: 21,9 s y 20,3 s (incluye la pausa entre apps). **625 consultas, 0 errores**, máximo 1032 ms. **CUMPLE**. Evidencia: `evidencias/STG11_dos_despliegues_seguidos.json`

## STG12 — Caída de ambas bases (corregido)
Pasos: los de STG09, con stg-v9, durante ~30 s.
Resultado observado: `/health` → 200 `degradado` con `origen_datos: cache` y `antiguedad_cache_s` creciente, en 5 ms. Al levantar las bases volvió solo a `ok` / `base`. **505 consultas, 0 errores**, máximo 63 ms. **CUMPLE**. Evidencia: `evidencias/STG12_caida_ambas_bases_corregido.json`

## STG13 — Un daño en los datos no se tapa con la copia
Qué queremos comprobar: que la copia en memoria no oculta datos dañados.
Pasos: `respaldar`, `simular-error` (DROP TABLE en el primario, replicado a la réplica), esperar 3 s, consultar y `restaurar`.
Resultado observado: `/health` → **503** `error_datos` (la copia se descartó). `/pedidos` → 502 por el reintento de NGINX ante 503 (hallazgo conocido de I06). Tras `restaurar`, el primer `/health` 200 llegó a los **3,19 s**: restauración ~0,6 s + refresco ≤1 s + `fail_timeout` de NGINX. **CUMPLE**. Evidencia: `evidencias/STG13_dano_datos_con_cache.txt`

## STG14 — Caída del primario (código final)
Resultado observado: primario detenido 20 s. **381 consultas, 0 errores**, máximo 47 ms. Al volver el primario, la réplica reanudó la replicación sola (`state = streaming`). **CUMPLE**. Evidencia: `evidencias/STG14_caida_primario_final.json`

# AWS (us-east-2, plan gratuito)

## AWS01 — Crear la pila de red
Qué queremos comprobar: que la plantilla `infra/aws/01-red.yaml` se despliega en la cuenta real pese a la SCP de la organización.
Pasos: `create-stack` de `nodo-ruta-red` en us-east-2 con `CidrAcceso` = IP del integrante (/32) y etiqueta `proyecto=nodo-ruta`; `wait stack-create-complete`; `describe-stacks`.
Resultado observado: **CREATE_COMPLETE** en ~1 min, con VPC, 2 subredes públicas, 2 privadas y los grupos `SgAlb`, `SgEc2` y `SgRds` exportados. Costo: USD 0 (sin NAT ni IP elástica). **CUMPLE**. Evidencia: `evidencias/AWS01_pila_red.json`

## AWS02 — Crear la pila de datos (RDS + S3)
Qué queremos comprobar: que la SCP deja crear RDS y S3 en us-east-2 y que la contraseña llega desde SSM sin estar en el repo.
Pasos: crear el parámetro SecureString `/nodo-ruta/db/password` (a mano, con `read -s`); `create-stack` de `nodo-ruta-datos`; `wait stack-create-complete`; `describe-stacks`.
Resultado observado: **CREATE_COMPLETE** en ~13 min. RDS PostgreSQL 17 (`db.t4g.micro`, Single-AZ, cifrada, sin acceso público) y bucket de respaldos creados. **CUMPLE**. Evidencia: `evidencias/AWS02_pila_datos.json`. Costo: RDS consume créditos mientras exista.

## AWS03 — Reparto entre dos zonas detrás del ALB
Qué queremos comprobar: que el ALB reparte entre las 2 EC2 (una por zona), que la app lee de RDS y que cada respuesta identifica la instancia.
Pasos: `create-stack` de `nodo-ruta-computo` (versión git `6f5a222`); esperar el arranque; consultar `/health` del ALB varias veces; `describe-target-health`.
Resultado observado: **CREATE_COMPLETE**; `/health` → `estado: ok`, `origen_datos: base` (RDS con los 6 pedidos cargados). Al principio solo respondía 2a: la EC2 B tardó ~8 min en construir las imágenes y estuvo `unhealthy` mientras tanto (el ALB no le mandó tráfico). Con ambas `healthy`, 8 solicitudes: 4 a `us-east-2a` y 4 a `us-east-2b`. **CUMPLE**. Evidencia: `evidencias/AWS03_reparto_dos_zonas.json`

## AWS04 — Caída de una instancia (EC2 B) y recuperación
Qué queremos comprobar: qué ve un cliente si una de las dos EC2 se detiene, cuánto tarda el ALB en sacarla y si vuelve sola al arrancarla.
Pasos (`infra/aws/PRUEBAS.md`): `monitorear.py` contra `/pedidos` del ALB durante 270 s cada 0,5 s; a los 20 s `stop-instances` de B; 30 s detenida; `start-instances`; un bucle anota la salud del target group cada ~2 s. Versión `d7b0acd`.
Resultado observado:
- **299 consultas, 5 errores (1,7 %)**: 4 × 502 y 1 *timeout*, todos entre **20:26:13,1 y 20:26:20,8**, es decir de 2,1 s a 9,8 s después de `STOP_B enviado` (20:26:11). **Después, 0 errores**, también cuando B volvió.
- El ALB marcó a B `unhealthy` en la lectura de las **20:26:24** (≤13 s tras la parada; el bucle muestrea cada ~2 s). Desde el último error, todo lo atendió A.
- B volvió **sola**: primera respuesta a las **20:27:40,6**, **40,6 s** después de `START_B enviado` (22 s después de `running`), sin tocar nada más. Los contenedores arrancaron por `--restart unless-stopped`. B estuvo 90,5 s sin responder en total.
- Latencia: mediana 217 ms, p95 1214 ms, máx. 2240 ms.
**CUMPLE** el criterio [S] (errores solo en una ventana corta alrededor de la parada, cero después, B vuelve sola antes de 270 s).
Hallazgo honesto: el ALB **no reintenta** contra la otra instancia, así que durante ~8 s (hasta que el health check de 2 × 5 s saca a B) algunas solicitudes fallan con 502. Mejora posible: sacar la instancia del target group antes de una parada planificada o bajar el umbral del health check. Evidencias: `evidencias/AWS04_caida_instancia_*`

## AWS05 — Respaldo a S3 y comprobación de integridad
Qué queremos comprobar: que `despliegue/aws/respaldar.sh` saca un `pg_dump` de RDS, lo deja en S3 (fuera del cómputo y de la base) con su SHA-256, y que el objeto es íntegro y legible.
Pasos (`infra/aws/PRUEBAS.md`): `respaldar.sh` en la EC2 A con `aws ssm send-command`; listar `respaldos/` en el bucket; `datos.sh comprobar` (vuelve a bajar el objeto, compara el SHA-256 y lee el índice con `pg_restore --list`).
Resultado observado: `estado: Success` en las dos órdenes. En S3 quedaron `respaldos/20261124_013921_manual.dump` (2915 bytes) y su `.sha256`. `COMPROBADO`: mismo sha256 `ee626042…564e` y 6 objetos en el índice, con los datos de `pedidos`. Tiempo total: ~13 s, de las 20:39:20 a las 20:39:33. **CUMPLE**. Evidencia: `evidencias/AWS05_respaldo_s3.txt`

## AWS06 — Alteración simulada y restauración desde S3 (primer intento, FALLÓ)
Qué queremos comprobar: que un daño en los datos se detecta y que se restaura desde S3, midiendo el tiempo de recuperación.
Pasos: monitor sobre `/health` del ALB 200 s; `datos.sh verificar` → `alterar` (DROP TABLE pedidos, con el respaldo de AWS05 comprobado antes) → `/health` → `restaurar`.
Resultado observado: `verificar` antes: `datos-v1 pedidos=6`. Tras alterar, `/health` del ALB → **503** (el daño se detecta y no se tapa). **`restaurar` falló** (`estado: Failed`): antes de restaurar guarda una copia `prerestauracion` del estado actual, y `respaldar.sh` se negó a subirla porque exige la tabla `pedidos`, que es justo lo que faltaba. No se tocó la base. El servicio quedó en 503: **180 errores de 197** entre 20:42:00 y el final del monitor. **NO CUMPLE**.
Corrección: commit `166ca8a`. La copia `prerestauracion` ya no exige `pedidos`, aunque sí que `pg_restore` pueda leerla. Evidencia: `evidencias/AWS06_restauracion_s3*`

## AWS06b — Restauración desde S3 con la corrección
Pasos: actualizar el repo de la EC2 A a `166ca8a` por SSM; monitor sobre `/health` 75 s; `datos.sh restaurar respaldos/20261124_013921_manual.dump`; `verificar`; listar el bucket.
Resultado observado: `/health` antes: **503**. `RESTAURAR` a las **20:50:20**: respaldo comprobado (mismo sha256), copia `20261124_015025_prerestauracion.dump` subida a S3, `Restaurado desde ...`, `datos-v1 pedidos=6` (iguales que antes del daño). **Primer 200 a las 20:50:28,6 → recuperación en 8,6 s** medida desde la orden, incluida la latencia de SSM. Los 11 errores son todos anteriores (último a las 20:50:27,9) y **después hay 0 errores**, con 34 respuestas de cada zona. SSM informó el fin a las 20:50:33. **CUMPLE**.
Lectura honesta: la recuperación con el procedimiento correcto tarda segundos, pero el incidente completo duró **~8,5 min** (20:42:00 → 20:50:28) por el defecto del script. Ensayar la restauración antes de necesitarla es lo que lo descubrió. Evidencia: `evidencias/AWS06b_restauracion_s3*`

## AWS08 — Interfaz y API por CloudFront (D16)
Qué queremos comprobar: que la interfaz se sirve por HTTPS desde S3 a través de CloudFront, que `/pedidos` y `/health` llegan al ALB sin caché y repartidas entre las dos zonas, y que los cambios de red y cómputo no reemplazaron recursos.
Pasos (`infra/aws/README.md`, "Pila del front"):
1. `update-stack` de `nodo-ruta-red`: `SgAlb` acepta la prefix list de CloudFront.
2. Revisión con change set y `update-stack` de `nodo-ruta-computo`: listener con 403 por defecto, regla `X-Origin-Verify` y regla de IP.
3. `create-stack` de `nodo-ruta-front`.
4. `scripts/publicar_front.py`.
5. Comprobaciones con `curl`.
Resultado observado:
- Change set del cómputo: `Listener Modify False` y 2 reglas `Add`. Las EC2 conservan sus ids (`i-0595…` e `i-0923…`) y el ALB directo sigue dando 200 desde la IP permitida.
- La SCP **sí permite crear CloudFront**. La distribución tardó **6 min 54 s** (21:36:49 → 21:43:43).
- `/` → 200 `text/html` (la interfaz). `http://` → **301** a `https://`. `/pedidos` → 200 JSON con 6 pedidos.
- 6 consultas a `/health`: alternan entre 2a y 2b (3 y 3).
- API con `x-cache: Miss from cloudfront` (sin caché). El `.js` de `assets/` sale con `cache-control: public,max-age=31536000,immutable`: `Miss` la primera vez y `Hit` la segunda.
- Listener: `fixed-response 403` por defecto, regla 1 `http-header` y regla 2 `source-ip`.
**CUMPLE**.
Diseñado, no probado (no se puede simular desde la IP permitida): el rechazo de otras IP en la CloudFront Function y en el grupo de seguridad, y el 403 del ALB ante un encabezado falso o ausente.
Hallazgo: `app.py` responde **501 a HEAD** (también directo al ALB; es comportamiento previo de la app), por eso `curl -I` por CloudFront muestra `Error from cloudfront`. Con GET todo responde 200.
Evidencias: `evidencias/AWS08_front_creacion.txt`, `evidencias/AWS08_publicacion.txt` y `evidencias/AWS08_front_cloudfront.txt`.

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
