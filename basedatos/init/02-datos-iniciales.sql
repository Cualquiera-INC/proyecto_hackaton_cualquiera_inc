-- Datos iniciales: los mismos 6 pedidos sintéticos de pedidos.json (datos-v1).
INSERT INTO metadatos (clave, valor) VALUES ('version', 'datos-v1');

INSERT INTO pedidos (id, zona, estado) VALUES
    ('PED-001', 'Norte',     'En ruta'),
    ('PED-002', 'Centro',    'Entregado'),
    ('PED-003', 'Sur',       'Pendiente'),
    ('PED-004', 'Occidente', 'En ruta'),
    ('PED-005', 'Oriente',   'Entregado'),
    ('PED-006', 'Centro',    'En preparación');
