# 01 · El reto y lo que pide

> Fuente: [recursos-reto/Ficha_del_reto.pdf](../recursos-reto/Ficha_del_reto.pdf) y [recursos-reto/GUIA_ESTUDIANTE.md](../recursos-reto/GUIA_ESTUDIANTE.md). Si algo de aquí contradice esos documentos, mandan ellos.

## El problema (caso ficticio)

Nodo Ruta S.A.S. tiene un servicio web para que operaciones consulte el estado de las entregas. Corre en **una sola instancia**, con los **datos dentro de la aplicación** y cambios hechos a mano. Si la instancia se cae o una actualización trae un error, las consultas dejan de responder, y no hay un procedimiento probado para recuperar los datos.

**El trabajo es de infraestructura, no de desarrollo:** la app ya viene hecha (Python, rutas `/`, `/health`, `/pedidos`, JSON con 6 pedidos y un identificador de versión).

## Qué hay que entregar (MVP)

| Requisito del reto | Cómo lo cumplimos | Dónde se ve |
|---|---|---|
| 2 instancias detrás de un punto de acceso común | `app1` + `app2` detrás de NGINX en `127.0.0.1:8080` | `despliegue/`, I01 |
| Datos fuera del sistema de archivos efímero | `data/` montada en solo lectura desde el disco | I04 |
| Respaldo y restauración definidos | `scripts/datos.py` + servicio `respaldo` cada 5 min, con SHA-256 | I05, I05c, I05d |
| Comprobar la salud | `/health` (lee los datos de verdad) + healthchecks de Compose | I02, I03 |
| Consultar registros | `docker compose logs` (NGINX registra qué instancia atendió) | I02b |
| Reconocer qué instancia atendió | Campo `instancia` (y `version_app`) en cada respuesta | todas |
| Archivos para recrear el despliegue | [README](../README.md) + `scripts/desplegar.py` | I06 |
| Esquema de arquitectura | [02-arquitectura.md](02-arquitectura.md) | — |
| Evidencias de las pruebas | [EVIDENCIAS.md](../EVIDENCIAS.md) | — |

## Pruebas mínimas (guía V2)

| ID | Prueba | Estado |
|---|---|---|
| I01 | Consultar por el acceso común y ver app1 y app2 | ✅ |
| I02 | Detener app1 y seguir consultando por app2; registrar errores y tiempo | ✅ |
| I03 | Recuperar app1 y ver otra vez las dos | ✅ |
| I04 | Recrear una instancia y comprobar que conserva los datos | ✅ |
| I05 | Alterar los datos, ver el 503, restaurar y comparar versión y contenido | ✅ |
| I06 | Repetir con otro integrante siguiendo las instrucciones del equipo | 🟡 parcial |

Extras del equipo: I07 (actualizar sin caída) e I08 (rollback automático).

## Reglas que no se negocian

1. **Solo datos sintéticos** del paquete. Nada de servicios reales.
2. **Cero costos.** En AWS: alerta de presupuesto antes de crear nada y destruir todo al terminar.
3. **Ningún secreto** en la imagen ni en el repositorio (`.env` está en `.gitignore`).
4. **Exposición mínima:** solo el proxy (o el balanceador) recibe tráfico.
5. **Pruebas destructivas solo sobre copias.** El respaldo vive fuera de lo que se modifica.
6. **Honestidad:** dos contenedores en un computador **no** son alta disponibilidad. Se dice "tolerancia a la caída de una instancia" y se separa lo **probado** de lo **solo diseñado**.
7. **Medir, no estimar:** los tiempos salen de scripts con marcas de tiempo.
8. **Cambios mínimos a la app:** solo lo necesario para observarla y desplegarla.

## Objetivos de recuperación

| Métrica | Objetivo | Medido en local |
|---|---|---|
| Caída de una instancia | 0 errores visibles | 0 errores (I02, I07) |
| RTO tras datos dañados | < 1 min con el procedimiento | 157 ms de restauración (I05c) |
| RPO (datos que se pueden perder) | ≤ 5 min | Respaldo cada 5 min |

## Calendario

- **Encuentro 1:** entender y planear (hecho).
- **Encuentro 2:** construir y probar (local hecho; AWS en curso).
- **Encuentro 3:** mejoras y pitch. Mejoras elegidas: rollback (hecho), auto-recuperación, página de estado y video de la demo.
