"""Consulta el servicio de forma continua mientras ocurre un despliegue o rollback.

Sirve como evidencia de "despliegue sin caída": registra cada consulta (hora,
código HTTP, instancia, versión de la app, milisegundos) y resume cuántos
errores hubo y en qué momento cambió la versión que responde.

  python scripts/monitorear.py --segundos 90 --salida evidencias/despliegue_v2.json

Se detiene al cumplir el tiempo o con Ctrl+C (la evidencia se guarda igual).
Código de salida 0 si no hubo ningún error.
"""
import argparse, collections, datetime, json, time, urllib.request, urllib.error
from pathlib import Path

p = argparse.ArgumentParser(description="Monitoreo continuo del servicio durante un despliegue.")
p.add_argument("url", nargs="?", default="http://127.0.0.1:8080/pedidos")
p.add_argument("--segundos", type=float, default=90, help="duración máxima (por defecto 90)")
p.add_argument("--intervalo", type=float, default=0.1, help="pausa entre consultas en segundos (por defecto 0.1)")
p.add_argument("--salida", default="evidencias/monitoreo.json")
a = p.parse_args()
target = Path(a.salida)
if target.exists():
    p.error("La salida ya existe. Use otro nombre para conservar la evidencia anterior")

rows, inicio = [], time.monotonic()
print(f"Monitoreando {a.url} durante {a.segundos:.0f} s (Ctrl+C para terminar antes)...", flush=True)
ultima, vistos = None, {}
try:
    while time.monotonic() - inicio < a.segundos:
        t0 = time.monotonic()
        row = {"consulta": len(rows) + 1, "fecha": datetime.datetime.now().isoformat(timespec="milliseconds")}
        try:
            with urllib.request.urlopen(a.url, timeout=5) as r:
                raw = r.read(); row["http"] = r.status
            data = json.loads(raw)
            row.update(instancia=data.get("instancia"), version_app=data.get("version_app"),
                       version_datos=data.get("version", data.get("version_datos")))
        except urllib.error.HTTPError as e:
            row.update(http=e.code, error=str(e))
        except (OSError, ValueError) as e:
            row.update(http=None, error=str(e))
        row["milisegundos"] = round((time.monotonic() - t0) * 1000, 1)
        rows.append(row)
        # Solo se imprime lo relevante: errores y cambios en las versiones que responden.
        if row.get("http") != 200:
            print(f"  {row['fecha']} ERROR http={row.get('http')} {row.get('error', '')}", flush=True)
        else:
            vistos[row["instancia"]] = row["version_app"]
            estado = dict(sorted(vistos.items()))
            if estado != ultima:
                print(f"  {row['fecha']} respondiendo: {estado}", flush=True)
                ultima = estado
        time.sleep(a.intervalo)
except KeyboardInterrupt:
    print("Detenido por el usuario.")

errores = [r for r in rows if r.get("http") != 200]
por_version = collections.Counter(r.get("version_app") for r in rows if r.get("http") == 200)
por_instancia = collections.Counter(f"{r.get('instancia')}@{r.get('version_app')}" for r in rows if r.get("http") == 200)
lat = sorted(r["milisegundos"] for r in rows if r.get("http") == 200)
resumen = {
    "url": a.url,
    "resultado": "SIN_CAIDA" if rows and not errores else "CON_ERRORES",
    "consultas": len(rows),
    "errores": len(errores),
    "duracion_s": round(time.monotonic() - inicio, 1),
    "respuestas_por_version": dict(por_version),
    "respuestas_por_instancia": dict(por_instancia),
    "latencia_ms": {"max": lat[-1], "p95": lat[int(len(lat) * 0.95) - 1] if len(lat) > 1 else lat[0],
                    "mediana": lat[len(lat) // 2]} if lat else {},
    "primer_error": errores[0]["fecha"] if errores else None,
    "ultimo_error": errores[-1]["fecha"] if errores else None,
}
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps({**resumen, "detalle": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(resumen, ensure_ascii=False, indent=2))
print("Evidencia guardada en", target)
raise SystemExit(0 if resumen["resultado"] == "SIN_CAIDA" else 1)
