# Despliegue sin caída y rollback — Nodo Ruta

Este es el despliegue propio del equipo. Resuelve la parte del reto que dice
*"cuando una actualización introduce un error, las consultas dejan de responder"*.
La configuración de `ayuda_opcional/` queda intacta como referencia.

> **Rama `staging`:** este stack ya no lee `data/pedidos.json`. Suma `postgres`, el microservicio `pedidos1`/`pedidos2` y un respaldo con `pg_dump`. La actualización escalonada recorre pedidos1 → pedidos2 → app1 → app2. El mecanismo de abajo es el mismo; el detalle de staging está en [docs/07-staging-microservicios-postgres.md](../docs/07-staging-microservicios-postgres.md).

## Qué cambia respecto a la ayuda opcional

| Problema en la referencia | Solución en `despliegue/` |
|---|---|
| `up -d --build` recrea app1 y app2 a la vez y el servicio se cae | `scripts/desplegar.py` actualiza **una instancia a la vez** |
| Si la versión nueva falla, las dos instancias quedan rotas | Comprueba la salud y la versión antes de seguir; si algo falla, hace **rollback automático** |
| Todas las imágenes se llaman `latest` y no se puede volver atrás | Imágenes con versión (`nodo-ruta:<version>`) e historial en `despliegue/estado.json` |
| No hay forma de saber qué código responde | `/health` y `/pedidos` incluyen `version_app` |
| Python como PID 1 ignora SIGTERM y Docker lo mata a la fuerza | `app.py` se apaga ordenadamente y termina las solicitudes en curso |
| Si un contenedor se cae, nadie lo levanta | `restart: unless-stopped` en los tres servicios |
| nginx espera 1 s antes de reintentar en la otra instancia | `proxy_connect_timeout 300ms` y DNS cada 2 s |
| El proxy no tiene healthcheck | Healthcheck propio en `/proxy-health` |
| Se monta un solo archivo de datos | Se monta la carpeta `data/`, lo que permite reemplazar el archivo de forma atómica |
| No hay interfaz web | La imagen del proxy (`Dockerfile.proxy`) construye `frontend-nodo/` y la sirve en `/`; la API sigue en `/pedidos` y `/health` |
| Los respaldos son manuales | Servicio `respaldo` (aporte de la solución local de Oscar): `datos.py respaldar` cada 5 min, nunca respalda un JSON dañado |

## Cómo funciona un despliegue

```
1. Construir nodo-ruta:<nueva>    ← el servicio sigue atendiendo con la versión actual
2. Precondición: app1, app2 y proxy sanos (si no, aborta sin tocar nada)
3. Recrear app1 con <nueva>       ← NGINX envía todo a app2 (versión actual)
4. Esperar: app1 healthy + /health dice version_app=<nueva> + el proxy ya la usa
5. Recrear app2 con <nueva>       ← NGINX envía todo a app1 (versión nueva)
6. Igual que el paso 4 para app2
   ✗ Si falla el paso 4 o el 6 → las instancias tocadas vuelven a la versión anterior
```

En ningún momento quedan las dos instancias fuera de servicio a la vez.

## Uso

Primero hay que detener el laboratorio de la ayuda opcional, porque usa el mismo puerto 8080:

```powershell
docker compose -f ayuda_opcional/compose.yaml down
python scripts/datos.py preparar        # una vez: crea despliegue/secretos/db_password.txt
```

| Acción | Comando |
|---|---|
| Desplegar una versión nueva (incluido el primer despliegue) | `python scripts/desplegar.py desplegar --version v1` |
| Volver a la versión anterior | `python scripts/desplegar.py rollback` |
| Volver a una versión concreta | `python scripts/desplegar.py rollback --version v1` |
| Ver la versión actual, el historial y las versiones disponibles | `python scripts/desplegar.py estado` |
| Monitorear el servicio durante un despliegue | `python scripts/monitorear.py --segundos 60 --salida evidencias/<nombre>.json` |
| Ver contenedores y registros | `docker compose -f despliegue/compose.yaml ps` / `logs --tail 50` |
| Apagar todo | `docker compose -f despliegue/compose.yaml down` |

- Si no se indica `--version`, se genera una con la fecha y el commit (por ejemplo `20261121-093000-b801c4d`).
- Para usar otro puerto: `$env:NODO_PUERTO='8081'` antes del primer despliegue. El puerto queda guardado en `despliegue/.env`.
- Códigos de salida: `0` éxito, `1` fallo (con rollback automático), `2` uso incorrecto. Así el script se puede llamar desde un pipeline (por ejemplo GitHub Actions) sin cambios.

## Demostración para la presentación (dos terminales)

**Terminal A** — consultas continuas como evidencia:
```powershell
python scripts/monitorear.py --segundos 60 --salida evidencias/despliegue_v2.json
```

**Terminal B**, mientras corre A:

1. **Despliegue sin caída:**
   ```powershell
   python scripts/desplegar.py desplegar --version v2
   ```
   En A se ve cómo `{'app1': 'v1', 'app2': 'v1'}` pasa a `{'app1': 'v2', 'app2': 'v1'}` y luego a `{'app1': 'v2', 'app2': 'v2'}`, con 0 errores.

2. **Versión con error y rollback automático:** añadir temporalmente en `app.py`, justo debajo de `port = int(...)`, la línea:
   ```python
       raise RuntimeError("BUG SIMULADO")
   ```
   y ejecutar:
   ```powershell
   python scripts/desplegar.py desplegar --version v3-roto
   ```
   El script detecta que app1 no arranca, la devuelve a v2 y termina con código 1. app2 nunca se tocó.
   **Después hay que quitar la línea de `app.py`.**

3. **Rollback manual a v1:**
   ```powershell
   python scripts/desplegar.py rollback
   ```

## Resultados de la prueba del 21/11/2026

Pruebas en local con Docker Desktop. El monitor hizo una consulta a `/pedidos` cada 0,1 s.

| Prueba | Duración | Consultas | Errores | Latencia máxima |
|---|---|---|---|---|
| Despliegue v1 → v2 | 9,4 s | 389 | **0** | — |
| Despliegue de v3-roto → rollback automático a v2 | 4,2 s | 345 | **0** | 313 ms (reintento en la otra instancia) |
| Rollback manual v2 → v1 | 8,1 s | 214 | **0** | 47 ms |

### Prueba desde Linux (21/11/2026)

El script se ejecutó desde un contenedor Alpine Linux (Python 3.14, Docker Compose v5.7) con proyecto `nodo-ruta-linux` en el puerto 8082. Se probaron:
- el despliegue inicial;
- un despliegue inmediatamente después del inicial;
- un rollback manual;
- una versión rota con rollback automático.

Durante las cuatro pruebas el monitor hizo **857 consultas sin ningún error**.

Esta prueba encontró un fallo que en Windows no apareció: justo después de arrancar, el healthcheck del proxy está en `starting` y el siguiente despliegue se cancelaba. Ya está corregido: la precondición espera hasta 30 s.

## En un servidor Linux

Requisitos:
- Docker Engine 25 o superior con el plugin `docker compose` (v2).
- Python 3.8 o superior.
- git.
- En Linux el comando suele ser `python3`:
  ```bash
  python3 scripts/datos.py preparar
  python3 scripts/desplegar.py desplegar --version v1
  ```

A tener en cuenta:
- **Acceso desde fuera:** por defecto el proxy solo escucha en `127.0.0.1`. En un servidor hay que ejecutar `export NODO_IP=0.0.0.0` antes del primer despliegue, y lo ideal es ponerlo detrás de HTTPS y de un firewall.
- **Permisos de Docker:** el usuario que despliega (también el de GitHub Actions) debe pertenecer al grupo `docker` (`sudo usermod -aG docker <usuario>`).
- **Permisos de los datos:** la app corre con el UID 10001, así que `data/` y `data/pedidos.json` deben poder leerse por "otros" (755 y 644, que es lo normal con `umask 022`).
- **SELinux** (RHEL, Fedora, Rocky): los bind mounts necesitan etiqueta. Hay que añadir `:z` al montaje o `bind: selinux: z` en `compose.yaml`. En Ubuntu y Debian no aplica.
- **GitHub Actions:** hay que usar `concurrency:` en el workflow para que dos despliegues no se ejecuten a la vez sobre el mismo servidor.
- **El historial de despliegues** (`despliegue/estado.json`) es local al servidor. Si se borra la carpeta, las imágenes siguen ahí y se puede volver a una versión con `rollback --version <v>`.

## Limitaciones

- Todo sigue corriendo en un solo computador y con un solo proxy: es un despliegue sin caída, **no alta disponibilidad**.
- El rollback revierte el código, no los datos. Para los datos están `scripts/datos.py respaldar` y `restaurar`.
- El healthcheck valida que la app arranca y lee los datos. Un error que no afecte a `/health` no se detectaría; se puede ampliar con pruebas de humo sobre `/pedidos`.
- Las imágenes antiguas se conservan para poder hacer rollback. Para limpiarlas: `docker image rm nodo-ruta:<version>`.
- Pendiente: un pipeline de GitHub Actions que ejecute `desplegar.py` en el servidor cuando esté disponible.
