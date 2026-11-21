# Frontend Nodo Ruta

Interfaz React (Vite + TypeScript) para consultar pedidos y el estado del servicio.

## Qué hace

- Muestra el estado de `/health` (instancia y versión de datos).
- Lista pedidos de `/pedidos`.
- Barra de búsqueda por **ID** de pedido.
- Solo lectura: no crea ni edita pedidos.

## Desarrollo local

1. Levanta el API (Compose o `python scripts/ejecutar_local.py`).
2. En esta carpeta:

```bash
npm install
npm run dev
```

Por defecto `.env.development` usa `VITE_API_URL=http://127.0.0.1:8080`.
También hay proxy Vite para `/pedidos` y `/health` si dejas la variable vacía.

## Variable de entorno

| Variable       | Uso |
|----------------|-----|
| `VITE_API_URL` | Base del API sin barra final. Vacío = mismo origen (NGINX / CloudFront). |

Ejemplo: ver `.env.example`.

## Producción (mismo origen)

```bash
VITE_API_URL= npm run build
```

`despliegue/Dockerfile.proxy` construye este front dentro de Docker y la imagen del proxy (`nodo-ruta-proxy`) sirve la SPA en `/`, mientras balancea `/pedidos` y `/health` hacia `app1`/`app2`. Se construye sola en el primer `python scripts/desplegar.py desplegar`. Si cambias el front, sube `PROXY_TAG` y reconstruye el proxy (ver los comentarios en `despliegue/compose.yaml`).

## CI

El workflow `.github/workflows/frontend.yml` instala, hace lint y genera el artefacto `frontend-dist`.
