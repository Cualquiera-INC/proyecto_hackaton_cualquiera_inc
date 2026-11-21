# 06 · Pitch (encuentro 3)

> Borrador. La duración exacta se confirma con la organización.

## Guion

| # | Bloque | Mensaje | Evidencia |
|---|---|---|---|
| 1 | El problema | "Si la única instancia cae, operaciones se queda sin consultar entregas, y nadie sabe cuánto tarda en volver ni si los datos son los correctos." | — |
| 2 | Antes / después | Una instancia con los datos adentro → dos instancias, datos fuera, respaldo verificado y despliegue sin caída | — |
| 3 | Arquitectura | Local (probado) y AWS (diseño / probado) | [02-arquitectura.md](02-arquitectura.md) |
| 4 | Demo 1 · Normal | Las consultas se reparten entre app1 y app2 | `monitorear.py` en pantalla |
| 5 | Demo 2 · Caída | Apagamos app1 en vivo y el servicio sigue | I02 / I02b |
| 6 | Demo 3 · Datos | Dañamos los datos, `/health` lo detecta, restauramos y verificamos | I05c (157 ms) |
| 7 | Demo 4 · Actualización | Versión nueva sin caída; versión rota que se revierte sola | I07 (0 errores / 708), I08 |
| 8 | Números | RTO, errores durante la caída y RPO ≤ 5 min | [EVIDENCIAS.md](../EVIDENCIAS.md) |
| 9 | Seguridad y costos | Controles aplicados y qué consumiría AWS | [04-seguridad-y-costos.md](04-seguridad-y-costos.md) |
| 10 | Honestidad | Probado vs. diseñado; por qué esto **no** es alta disponibilidad | Tabla de [02-arquitectura.md](02-arquitectura.md) |
| 11 | Próximos pasos | Escrituras con promoción de la réplica, implementación en AWS con CloudFormation, alertas | [03-decisiones.md](03-decisiones.md) |

**Frase para la coordinación logística (público no técnico):**
> "Si se cae una de las dos copias del servicio, las consultas siguen funcionando. Si los datos se dañan, los recuperamos en menos de un segundo y verificamos que sean los correctos. Si publicamos una versión con errores, el sistema vuelve solo a la anterior. Lo que no cubrimos en local es que se caiga el computador completo; para eso está el diseño en AWS."

**Si nos preguntan por el cambio frente a la ficha:** la ficha inicial proponía microservicios y PostgreSQL. Al recibir el paquete los descartamos (D9): la app es de solo consulta, con 6 pedidos. Después el equipo los reabrió (D12) para que los datos puedan recibir cambios desde varios puntos, y esta vez con 14 pruebas medidas (STG01–STG14). Decidimos con evidencia, y reconocemos lo que empeora: más piezas que operar, escrituras que dependen del primario y primario y réplica en la misma máquina.

## Ficha de la solución (enviada en el encuentro 1)

Se conserva como registro de lo que se presentó.

**Solución:** convertir el servicio de consulta de entregas, que corre en una sola instancia con los datos dentro de la app, en un despliegue con contenedores reproducible y automatizado. *(La ficha original describía 3 microservicios y PostgreSQL; ver D9 y D12.)*

**MVP:**
- balanceador NGINX como punto de acceso común;
- instancias replicadas que indican cuál atendió;
- datos persistentes fuera del contenedor;
- chequeos de salud y registros;
- respaldo y restauración verificados, con RTO y RPO medidos;
- despliegue automatizado sin secretos en el código.

**Pruebas comprometidas:**
1. Conmutación ante la caída de una instancia (como máximo 1 error durante la conmutación). → I02: 0 errores.
2. Persistencia al destruir y recrear los contenedores. → I04.
3. Respaldo, alteración, restauración y RTO registrado en segundos. → I05 / I05c.
