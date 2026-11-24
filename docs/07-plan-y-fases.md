# 07 · Estado y próximas fases

> Actualizado el 24-11-2026. Cuando se cierre una tarea, márquenla aquí en el mismo PR.

## Lo que tenemos (probado en local)

| Pieza | Qué es | Evidencia |
|---|---|---|
| **2 instancias de la app** | `app1` y `app2`, la misma imagen `nodo-ruta:<versión>`; cada respuesta dice `instancia` y `version_app` | I01 |
| **Proxy NGINX** | Único puerto (`127.0.0.1:8080`). Sirve la interfaz web en `/` y reparte `/pedidos` y `/health` entre las dos instancias, con reintento si una falla | I02, I07b |
| **Interfaz web** | React + Vite de solo lectura (estado, pedidos, búsqueda por ID), construida dentro de la imagen del proxy | I07b |
| **Datos fuera del contenedor** | `data/pedidos.json` montado en solo lectura; el original del reto queda intacto | I04 |
| **Respaldo automático** | Contenedor `respaldo`: copia + SHA-256 cada 5 min; nunca respalda un archivo dañado | I05, respaldo automático |
| **Restauración verificada** | `datos.py restaurar` comprueba la huella antes de escribir; el servicio vuelve en 157 ms | I05c, I05d |
| **Despliegue sin caída + rollback** | `desplegar.py`: una instancia a la vez, rollback automático si la nueva falla | I07 (0 errores en 708 consultas), I08 |
| **CI en GitHub Actions** | Build del frontend + prueba de punta a punta del despliegue en Linux en cada PR | checks de los PR #7 y #8 |
| **PostgreSQL + microservicio de pedidos** | `pedidos1`/`pedidos2` (solo lectura, copia en memoria), primario + réplica en caliente, respaldo con `pg_dump`. Tolera la caída de una base | STG01–STG14 |
| **Documentación** | `docs/01` a `docs/08`, `EVIDENCIAS.md`, README | — |

**Lo que todavía no está demostrado:** que el servicio sobreviva a la caída de una **máquina** completa, el health check activo, los respaldos fuera del computador y HTTPS. Todo eso es el objetivo de AWS.

## Fases

```mermaid
flowchart LR
    F1["Fase 1<br/>MVP local<br/>✅ hecho"] --> F2["Fase 2<br/>Pulir local<br/>⏳"]
    F2 --> F3["Fase 3<br/>Preparar AWS<br/>⏳"]
    F3 --> F4["Fase 4<br/>Construir en AWS<br/>⏳"]
    F4 --> F5["Fase 5<br/>Probar en AWS<br/>y destruir"]
    F5 --> F6["Fase 6 (E3)<br/>Mejoras, video<br/>y pitch"]
```

### Fase 2 · Pulir lo local (un PR pequeño, ~1 h)

| Tarea | Por qué | Responsable |
|---|---|---|
| `desplegar.py levantar` para encender la versión guardada después de un `down`, y corregir el mensaje que hoy sugiere `rollback` | Hoy, tras un `down`, el script obliga a inventar una versión nueva | [asignar] |
| Quitar `http_503` de `proxy_next_upstream` | Con datos dañados el usuario ve 502 y las instancias quedan fuera hasta 3 s | [asignar] |
| Fijar `python:3.12-slim` en el `Dockerfile` y `server_tokens off` | Reproducibilidad (hoy instala 3.15) y no mostrar la versión de NGINX | [asignar] |
| Guardar la evidencia de I08 (`evidencias/I08_rollback_automatico.json`) | Es la única prueba sin archivo | [asignar] |
| **I06 completa:** alguien que no haya tocado el código despliega siguiendo solo el README | La exige la guía del reto | [asignar] |

### Fase 3 · Preparar AWS (antes de crear cualquier recurso)

| Tarea | Detalle |
|---|---|
| **Alerta de presupuesto** | ✅ Hecha (21-11): `nodo-ruta-mensual`, USD 5 al mes sin contar créditos, avisos al 50 % y al 100 % |
| **Acceso de GitHub a AWS sin claves** | ✅ OIDC probado (21-11): rol `github-actions-nodo-ruta`, solo `main`, sin permisos todavía |
| **Dónde vive PostgreSQL en AWS** | ✅ Decidido (D13): 2 EC2 + RDS PostgreSQL Single-AZ (`t3.micro` o `t4g.micro`). Sin Multi-AZ en el plan gratuito |
| Usuarios IAM para el equipo | Nadie trabaja con el usuario raíz; permisos mínimos |
| Región | ✅ **us-east-2 (Ohio)**: es la única donde la política de la organización permite EC2, CloudFormation y RDS. Todo comando y plantilla usa `--region us-east-2` |
| **Decidir cómo se sirve la interfaz** | ✅ Decidido (D16, 23-11): CloudFront + S3 (la otra opción era la imagen `nodo-ruta-proxy` en cada EC2). Plantilla `infra/aws/04-front.yaml` **desplegada y probada** (AWS08) |
| Registro de imágenes | Propuesta: GHCR público, publicado desde GitHub Actions (sin costo y sin secretos) |
| Etiqueta común | `proyecto=nodo-ruta` en todo, para encontrarlo y borrarlo |
| Rama `staging` | Su contenido (PostgreSQL + microservicio) se integra a `main`; después se puede borrar la rama |

### Fase 4 · Construir en AWS (`infra/aws/`)

Plantillas de **CloudFormation** en `infra/aws/` para crear y destruir con una pila (D14):

1. **S3** con versiones: `actual/pedidos.json` y `respaldos/`.
2. **Imagen** construida una sola vez y publicada (GitHub Actions → GHCR).
3. **Rol IAM** para las EC2: solo lectura de `actual/*` en S3 y escritura de logs.
4. **2 EC2** en dos zonas, con Docker, la app montando `/data` y una tarea que sincroniza desde S3 cada 10 s con reemplazo atómico.
5. **ALB** + target group con health check a `/health`. Security groups: las EC2 solo aceptan tráfico del ALB y no tienen SSH (se usa Session Manager).
6. **CloudWatch Logs** con retención corta.
7. CloudFront + S3 para la interfaz (D16, `04-front.yaml`; pruebas en AWS08).

**Avance (23-11):** plantilla de red `infra/aws/01-red.yaml` escrita, validada y **desplegada** en us-east-2 como pila `nodo-ruta-red` (CREATE_COMPLETE, evidencia AWS01). Instrucciones en `infra/aws/README.md`. **Avance (23-11, rama `feat/infra-datos`):** `infra/aws/02-datos.yaml` (RDS PostgreSQL 17 Single-AZ, bucket S3 de respaldos, contrasena en SSM SecureString) escrita, validada y **desplegada** como pila `nodo-ruta-datos` (CREATE_COMPLETE, evidencia AWS02; RDS consume creditos mientras exista). **Avance (23-11, rama `feat/infra-computo`):** `infra/aws/03-computo.yaml` (2 EC2 por zona, ALB HTTP con health check a `/health` cada 5 s, rol de mínimo privilegio, sin SSH) escrita y **validada** con ValidateTemplate (después desplegada y probada). **Avance (23-11, rama `feat/infra-front`):** D16, `infra/aws/04-front.yaml` (S3 privado + CloudFront), regla de la prefix list en `01-red.yaml`, listener con 403 y reglas en `03-computo.yaml` y `scripts/publicar_front.py`; **desplegadas y probadas** (red y cómputo actualizados sin reemplazar recursos; front en `https://<id>.cloudfront.net`, evidencia AWS08). Carga inicial de la base y respaldo manual a S3 en `despliegue/aws/` y `basedatos/aws/` (D15).

**Avance (24-11, rama `feat/despliegue-automatico`):** D17, `scripts/aws_nodo.py` (`desplegar`, `estado`, `probar`, `destruir`, `--simular`) reemplaza los bloques manuales de `infra/aws/README.md` y `PRUEBAS.md`. **Probado solo con lecturas y respuestas simuladas; falta la primera ejecución real** (crear, probar y destruir en una misma sesión, con `--evidencia`). Pendiente de decisión: GitHub Actions con OIDC (hay que dar permisos de despliegue al rol `github-actions-nodo-ruta`).

> Los puntos 1, 3 y 4 asumían los datos como JSON en S3. Con D13 cambian: S3 solo guarda respaldos, las EC2 corren `app` + `pedidos` sin sincronizar nada y se suma una instancia RDS en subred privada (con su grupo de seguridad). Esta lista se reescribe al empezar las plantillas de CloudFormation.

### Fase 5 · Probar en AWS y destruir

| Prueba | Qué demuestra |
|---|---|
| I01–I05 en la nube | Lo mismo que en local, ahora con el ALB y S3 |
| **Apagar una EC2 completa** | Tolerancia a la caída de una máquina, imposible de demostrar en local |
| Restaurar una versión anterior en S3 | Respaldo fuera del cómputo; RTO medido, incluido el intervalo de sincronización |
| Medir errores durante la caída | El ALB no reintenta como NGINX: se reporta lo que salga, tal cual |
| **Destruir todo** y revisar facturación | Regla de costo cero (lista en `docs/04`) |

### Fase 6 · Encuentro 3: mejoras y pitch

- **Mejoras elegidas:** rollback (✅ hecho), auto-recuperación (en AWS: `restart:` + health check del ALB), página de estado (✅ la interfaz ya muestra el estado) y **video de la demo** (grabar local y AWS antes de destruir).
- Guion del pitch en `docs/06-pitch.md`, con los números finales de `EVIDENCIAS.md`.
- Tabla final de **probado vs. diseñado** actualizada.
