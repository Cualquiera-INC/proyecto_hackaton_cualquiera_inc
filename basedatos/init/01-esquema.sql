-- Esquema de Nodo Ruta (staging). PostgreSQL lo ejecuta UNA sola vez, cuando
-- el volumen de datos está vacío (primer arranque del contenedor "postgres").
-- Solo datos sintéticos: nunca cargar pedidos reales.

-- Metadatos del conjunto de datos; "version" equivale al campo version de pedidos.json.
CREATE TABLE metadatos (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE pedidos (
    id          TEXT PRIMARY KEY CHECK (id ~ '^PED-[0-9]{3,}$'),
    zona        TEXT NOT NULL,
    estado      TEXT NOT NULL CHECK (estado IN ('Pendiente', 'En preparación', 'En ruta', 'Entregado')),
    actualizado TIMESTAMPTZ NOT NULL DEFAULT now()
);
