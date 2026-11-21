# Nodo Ruta — despliegue y recuperación de un servicio de consulta

Reto 16 de la hackatón EstudIA (nube e infraestructura, nivel intermedio). Caso **ficticio** con datos sintéticos.

Dos instancias de la app detrás de NGINX, datos fuera de los contenedores, respaldo automático con verificación de integridad y despliegue de versiones nuevas sin caída, con rollback. Costo $0 en local; en preparación en AWS (plan gratuito).

| Quiero… | Ir a |
|---|---|
| Entender el reto y lo que pide | [docs/01-reto-y-requisitos.md](docs/01-reto-y-requisitos.md) |
| Ver la arquitectura (local y AWS) | [docs/02-arquitectura.md](docs/02-arquitectura.md) · [diagrama visual](docs/diagrama_solucion_local.html) |
| Saber por qué se decidió cada cosa | [docs/03-decisiones.md](docs/03-decisiones.md) |
| Seguridad y costos | [docs/04-seguridad-y-costos.md](docs/04-seguridad-y-costos.md) |
| Entender cómo funciona cada pieza | [docs/05-como-funciona-la-app.md](docs/05-como-funciona-la-app.md) |
| Ver los resultados de las pruebas | [EVIDENCIAS.md](EVIDENCIAS.md) |
| Detalle del despliegue y el rollback | [despliegue/README.md](despliegue/README.md) |
| Material original del reto | [recursos-reto/](recursos-reto/) |

## Levantar el servicio

Requisitos: Python 3 y Docker **iniciado** (Docker Desktop u OrbStack). En Windows usa `py` si ese es tu comando; en Linux, `python3`.

```text
python scripts/datos.py preparar                       # solo la primera vez: crea data/pedidos.json
python scripts/desplegar.py desplegar --version v1     # levanta app1, app2, proxy y respaldo
python scripts/desplegar.py estado                     # versión actual e historial
```

Abre http://127.0.0.1:8080/health o http://127.0.0.1:8080/pedidos. El campo `instancia` va alternando entre `app1` y `app2`.

Interfaz web (opcional): con el servicio arriba, entra a `frontend-nodo/` y ejecuta `npm install` y luego `npm run dev` (ver [frontend-nodo/README.md](frontend-nodo/README.md)).

| Acción | Comando |
|---|---|
| Publicar una versión nueva (sin caída) | `python scripts/desplegar.py desplegar --version v2` |
| Volver a la versión anterior | `python scripts/desplegar.py rollback` |
| Ver contenedores / registros | `docker compose -f despliegue/compose.yaml ps` / `logs --tail 50` |
| Apagar todo | `docker compose -f despliegue/compose.yaml down` |

`data/`, `respaldos/` y `evidencias/` se conservan al apagar. Si el puerto 8080 está ocupado, define `NODO_PUERTO` antes del primer despliegue (ver [despliegue/README.md](despliegue/README.md)).

## Pruebas

Cada prueba guarda su evidencia en `evidencias/`. Usa un nombre nuevo en cada repetición: los scripts no sobrescriben.

```text
# I01 acceso común
python scripts/verificar_servicio.py --esperadas app1,app2 --salida evidencias/I01_<fecha>.json
# I02 caída de app1  /  I03 recuperación
docker compose -f despliegue/compose.yaml stop app1
python scripts/verificar_servicio.py --esperadas app2 --salida evidencias/I02_<fecha>.json
docker compose -f despliegue/compose.yaml start app1
# I04 recrear sin perder datos
docker compose -f despliegue/compose.yaml up -d --force-recreate --no-deps app1
# I05 datos alterados -> restaurar
python scripts/datos.py simular-error
python scripts/datos.py restaurar --respaldo respaldos/<ARCHIVO>.json
# I07 despliegue sin caída (en otra terminal, mientras corre el monitor)
python scripts/monitorear.py --segundos 120 --salida evidencias/I07_<fecha>.json
```

**I06:** otra persona del equipo repite todo desde este README en su computador y lo registra en [EVIDENCIAS.md](EVIDENCIAS.md).

## Estructura

```
app.py  Dockerfile  pedidos.json   app del reto (cambios mínimos) y datos originales
despliegue/                        stack oficial: compose.yaml + nginx.conf
scripts/                           desplegar, datos, verificar_servicio, monitorear, ejecutar_local
evidencias/                        resultados de las pruebas (el prefijo es el ID)
docs/                              documentación del equipo
frontend-nodo/                     interfaz web React + Vite de solo lectura (ver su README)
.github/workflows/                 CI: frontend y contenedores
ayuda_opcional/                    configuración de referencia del reto (no oficial) + Dockerfile.proxy de la interfaz
recursos-reto/                     ficha, guía y plantilla originales
```

## Límites (dichos con honestidad)

- En local todo corre en **un solo computador**: es tolerancia a la caída de **una instancia**, no alta disponibilidad.
- El archivo de datos es compartido: si se daña, fallan las dos instancias hasta restaurar.
- La tolerancia a la caída de una máquina, el health check activo y los respaldos fuera del equipo son el objetivo del despliegue en AWS ([docs/02-arquitectura.md](docs/02-arquitectura.md)).
