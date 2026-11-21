# Registro del equipo
Equipo: Cualquiera INC
Integrantes y responsabilidades: [completar]
Fecha: 21-11-2026 (primera ejecución completa)
Modalidad: **contenedores locales** (Docker Desktop 29.9.3 en Windows 11). La nube queda como diseño: [docs/nube-diseno.md](docs/nube-diseno.md)
Arquitectura elegida y motivo: NGINX (`127.0.0.1:8080`) delante de app1 y app2, que comparten `data/pedidos.json` montado en solo lectura, y un servicio `respaldo` que copia cada 5 min a `respaldos/` con SHA-256. Es costo $0 y nos deja hacer pruebas destructivas controladas.
Ayudas utilizadas y cambios realizados: base `ayuda_opcional/compose.yaml` y `nginx.conf` (este último sin cambios). Añadimos `restart: unless-stopped`, el servicio `respaldo` y, en `app.py`, el hostname como identificador si falta `INSTANCE_ID`.
Recursos, permisos y posibles costos: solo CPU, memoria y disco del computador. No hay cuentas de nube ni secretos.

# Fichas de prueba
Las evidencias JSON están en `evidencias/` y las genera `scripts/verificar_servicio.py` (10 consultas secuenciales; no es una prueba de carga). Horas en UTC.

## I01 — Acceso común
Qué queremos comprobar: que el punto de acceso común responde y que se ven las dos instancias.
Versión y estado inicial: `datos-v1`, app1 y app2 healthy.
Resultado observado: 10/10 HTTP 200, con app1 y app2 alternando. **CUMPLE**. Evidencia: `evidencias/I01_inicio.json`

## I02 — Caída de app1
Pasos: `docker compose stop app1` (13:26:38) y consultar enseguida.
Resultado observado: 10/10 HTTP 200, todas atendidas por app2. **0 errores**. Una consulta tardó 1015 ms frente a 0–32 ms en las demás: es el `proxy_connect_timeout 1s` de NGINX antes de reintentar en app2 (detección pasiva). **CUMPLE**. Evidencia: `evidencias/I02_fallo_app1.json`

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

## I02b — Caída de app1 con registros
Qué queremos comprobar: relacionar cada consulta con su código HTTP y con la instancia que la atendió (la ficha pide "consultar sus registros").
Pasos: `docker compose stop app1` (13:43:39 UTC), `verificar_servicio.py`, y guardar `docker compose ps` y `docker compose logs --timestamps --tail 40 proxy app1 app2`.
Resultado observado: 10/10 HTTP 200 por app2. **CUMPLE**. El registro del proxy muestra el mecanismo:
```text
[error] upstream timed out ... while connecting to upstream ... upstream: "http://172.18.0.3:8080/pedidos"
"GET /pedidos HTTP/1.1" 200 upstream=172.18.0.3:8080, 172.18.0.4:8080 upstream_status=504, 200
```
NGINX intentó app1 (172.18.0.3), agotó el tiempo de conexión de 1 s y reintentó en app2 (172.18.0.4). El usuario recibió 200, con un segundo de demora. Evidencias: `evidencias/I02b_registros.txt` (incluye las IP de cada instancia) y `evidencias/I02b_fallo_app1.json`

## I05c — Tiempo de recuperación de la restauración
Qué queremos comprobar: el tiempo de la restauración sola, sin las consultas de diagnóstico que inflaron I05.
Pasos: `simular-error` (/health → 503) y luego `restaurar`, consultando `/health` cada 50 ms hasta obtener 200 con `datos-v1`.
Resultado observado: el comando `restaurar` tardó **110 ms** y el primer 200 correcto llegó a los **157 ms**. **CUMPLE**.
Hallazgo: la verificación inmediata (`I05c_restaurado.json`) vio solo app1. Mientras los datos estaban alterados, app2 devolvió 503 y NGINX la sacó de la rotación durante `fail_timeout=5s` (`max_fails=1`). Repetida a los 6 s (`I05c_restaurado_tras_5s.json`), aparecen app1 y app2. Es decir, **el servicio vuelve en ~0,2 s, pero el reparto entre las dos instancias tarda hasta 5 s más**. Evidencia: `evidencias/I05c_rto_restauracion.txt`

## I07 — Elegir el punto de recuperación
Qué queremos comprobar: que podemos volver a una versión concreta, no solo que el archivo abre (es la prueba opcional de la guía).
Pasos: se cambió la copia de trabajo a `datos-v2` (PED-003: Pendiente → Entregado), se respaldó y se comprobó que el servicio la publicaba. Después se restauró el respaldo de `datos-v1` (`respaldos/20261121_132624_895735.json`).
Resultado observado: el servicio pasó de `datos-v2`/Entregado a `datos-v1`/Pendiente con app1 y app2 en 200. El contenido es igual al `pedidos.json` original y el SHA-256 coincide con el respaldo elegido. El respaldo de v2 se conserva. **CUMPLE**. Evidencias: `evidencias/I07_punto_recuperacion.txt`, `I07a_v2_publicada.json` y `I07b_vuelta_a_v1.json`

## Respaldo automático
Resultado observado: el servicio `respaldo` creó copias cada 5 min (13:26, 13:31, 13:36 y, tras reiniciar el stack, 13:43 UTC). Las 5 copias tienen la huella SHA-256 correcta. Con datos corruptos se negó a respaldar (ver I05). **CUMPLE**. Evidencia: `evidencias/respaldo_automatico.txt`
Hallazgo: los nombres de los respaldos del contenedor usan la hora UTC, pero `datos.py respaldar` ejecutado a mano en Windows usa la hora local (UTC-5). Por eso el orden por nombre no es cronológico: hay que elegir el respaldo por su `version`, no por el nombre.

## I06 — Repetir con otro integrante
Responsable: [completar]. Seguir el [README](README.md) en otro PC y registrar las diferencias. **NO REALIZADO** todavía.

# Cierre
Qué funciona realmente: I01–I05, I02b, I05c e I07 en local; el respaldo automático validado y la restauración con verificación de huella (≈0,2 s).
Qué quedó como propuesta o pendiente: el despliegue en nube (solo diseño), I06, la rotación de respaldos y el respaldo fuera del computador.
Procedimiento para recrear y recuperar: [README](README.md).
Limitaciones y cambios para el encuentro 3: un solo computador no es alta disponibilidad; el JSON compartido es un punto único de fallo; NGINX libre solo detecta fallos de forma pasiva y, tras un incidente de datos, saca la instancia de la rotación hasta por 5 s; los nombres de los respaldos mezclan UTC y hora local. Ideas para E3: servir el "último dato bueno" en memoria cuando el JSON esté corrupto, copiar los respaldos fuera del equipo y un SLO medible.
