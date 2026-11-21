import { useEffect, useMemo, useState, type SubmitEvent } from "react";
import { apiBaseLabel, fetchHealth, fetchPedidos } from "./api";
import { estadoTone } from "./estado";
import type { HealthState, Pedido, PedidosResponse } from "./types";
import "./App.css";

type PedidosState =
  | { status: "loading" }
  | { status: "ok"; data: PedidosResponse }
  | { status: "error"; message: string; http?: number };

function App() {
  const [health, setHealth] = useState<HealthState>({ status: "loading" });
  const [pedidos, setPedidos] = useState<PedidosState>({ status: "loading" });
  const [query, setQuery] = useState("");
  const [applied, setApplied] = useState("");

  async function loadAll(opts?: { showLoading?: boolean }) {
    if (opts?.showLoading) {
      setHealth({ status: "loading" });
      setPedidos({ status: "loading" });
    }

    const [h, p] = await Promise.allSettled([fetchHealth(), fetchPedidos()]);

    if (h.status === "fulfilled") {
      setHealth({ status: "ok", data: h.value.data });
    } else {
      const err = h.reason as { message?: string; http?: number };
      setHealth({
        status: "error",
        message: err?.message ?? "No se pudo consultar /health",
        http: err?.http,
      });
    }

    if (p.status === "fulfilled") {
      setPedidos({ status: "ok", data: p.value.data });
    } else {
      const err = p.reason as { message?: string; http?: number };
      setPedidos({
        status: "error",
        message: err?.message ?? "No se pudo consultar /pedidos",
        http: err?.http,
      });
    }
  }

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [h, p] = await Promise.allSettled([fetchHealth(), fetchPedidos()]);
      if (cancelled) return;

      if (h.status === "fulfilled") {
        setHealth({ status: "ok", data: h.value.data });
      } else {
        const err = h.reason as { message?: string; http?: number };
        setHealth({
          status: "error",
          message: err?.message ?? "No se pudo consultar /health",
          http: err?.http,
        });
      }

      if (p.status === "fulfilled") {
        setPedidos({ status: "ok", data: p.value.data });
      } else {
        const err = p.reason as { message?: string; http?: number };
        setPedidos({
          status: "error",
          message: err?.message ?? "No se pudo consultar /pedidos",
          http: err?.http,
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered: Pedido[] = useMemo(() => {
    if (pedidos.status !== "ok") return [];
    const q = applied.trim().toLowerCase();
    if (!q) return pedidos.data.pedidos;
    return pedidos.data.pedidos.filter((item) =>
      item.id.toLowerCase().includes(q),
    );
  }, [pedidos, applied]);

  function onSearch(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    setApplied(query.trim());
  }

  return (
    <div className="app">
      <header className="brand">
        <img
          className="brand__mark"
          src="/logo.png"
          width={64}
          height={64}
          alt="Nodo Ruta"
        />
        <div className="brand__text">
          <h1>Nodo Ruta</h1>
          <p>Consulta el estado de entregas del equipo operativo.</p>
        </div>
      </header>

      <section className="status-bar" aria-live="polite">
        {health.status === "loading" && (
          <span className="status-pill" data-state="loading">
            <span className="status-pill__dot" aria-hidden />
            Comprobando servicio…
          </span>
        )}
        {health.status === "ok" && (
          <span className="status-pill" data-state="ok">
            <span className="status-pill__dot" aria-hidden />
            Servicio disponible
          </span>
        )}
        {health.status === "error" && (
          <span className="status-pill" data-state="error">
            <span className="status-pill__dot" aria-hidden />
            Servicio no disponible{health.http ? ` (${health.http})` : ""}
          </span>
        )}

        {health.status === "ok" && (
          <>
            <span className="status-meta">
              instancia <strong>{health.data.instancia}</strong>
            </span>
            <span className="status-meta">
              datos <strong>{health.data.version_datos ?? "—"}</strong>
            </span>
          </>
        )}
        {pedidos.status === "ok" && health.status !== "ok" && (
          <span className="status-meta">
            instancia <strong>{pedidos.data.instancia}</strong>
          </span>
        )}
        {pedidos.status === "ok" && (
          <span className="status-meta">
            versión <strong>{pedidos.data.version}</strong>
          </span>
        )}
      </section>

      <form className="search" onSubmit={onSearch}>
        <label htmlFor="pedido-id">Buscar pedido por ID</label>
        <div className="search__row">
          <input
            id="pedido-id"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ej. PED-001"
            autoComplete="off"
            spellCheck={false}
          />
          <button type="submit">Buscar</button>
        </div>
      </form>

      <section className="panel">
        <div className="panel__head">
          <h2>Pedidos</h2>
          <span>
            {pedidos.status === "ok"
              ? `${filtered.length} de ${pedidos.data.pedidos.length}`
              : "—"}
          </span>
        </div>

        {pedidos.status === "loading" && (
          <p className="message">Cargando pedidos…</p>
        )}

        {pedidos.status === "error" && (
          <div className="message message--error" role="alert">
            <p>
              {pedidos.message}
              {pedidos.http ? ` · HTTP ${pedidos.http}` : ""}
            </p>
            <div
              className="actions"
              style={{ justifyContent: "center", marginTop: "0.85rem" }}
            >
              <button
                type="button"
                className="ghost"
                onClick={() => void loadAll({ showLoading: true })}
              >
                Reintentar
              </button>
            </div>
          </div>
        )}

        {pedidos.status === "ok" && filtered.length === 0 && (
          <p className="message">
            No hay pedidos que coincidan con «{applied}».
          </p>
        )}

        {pedidos.status === "ok" && filtered.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Zona</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((pedido) => {
                const hit =
                  applied.trim().length > 0 &&
                  pedido.id
                    .toLowerCase()
                    .includes(applied.trim().toLowerCase());
                return (
                  <tr key={pedido.id} className={hit ? "is-hit" : undefined}>
                    <td className="id">{pedido.id}</td>
                    <td>{pedido.zona}</td>
                    <td>
                      <span
                        className="badge"
                        data-tone={estadoTone(pedido.estado)}
                      >
                        {pedido.estado}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      <div className="actions">
        <button
          type="button"
          className="ghost"
          onClick={() => void loadAll({ showLoading: true })}
        >
          Actualizar
        </button>
        {applied && (
          <button
            type="button"
            className="ghost"
            onClick={() => {
              setQuery("");
              setApplied("");
            }}
          >
            Limpiar búsqueda
          </button>
        )}
      </div>

      <p className="footer-note">
        API: {apiBaseLabel()} · Solo lectura · Caso ficticio EstudIA
      </p>
    </div>
  );
}

export default App;
