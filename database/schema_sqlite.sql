-- Sistema Automatizado de Control de Inventarios y Gestión de Ventas - M&S, C.A.
-- Esquema para SQLite (versión portátil que usa la aplicación). Misma estructura del modelo E-R del informe.
CREATE TABLE IF NOT EXISTS categoria (
  id_categoria INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS producto (
  id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT NOT NULL UNIQUE,
  nombre TEXT NOT NULL,
  id_categoria INTEGER NOT NULL REFERENCES categoria(id_categoria),
  tipo TEXT NOT NULL CHECK (tipo IN ('PRODUCTO','INSUMO')),
  unidad_medida TEXT NOT NULL,
  precio_venta REAL NOT NULL DEFAULT 0 CHECK (precio_venta >= 0),
  costo REAL NOT NULL DEFAULT 0 CHECK (costo >= 0),
  stock_actual REAL NOT NULL DEFAULT 0 CHECK (stock_actual >= 0),
  stock_minimo REAL NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
  activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1))
);
CREATE TABLE IF NOT EXISTS proveedor (
  id_proveedor INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL,
  rif TEXT UNIQUE,
  telefono TEXT,
  direccion TEXT
);
CREATE TABLE IF NOT EXISTS cliente (
  id_cliente INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL,
  cedula_rif TEXT UNIQUE,
  telefono TEXT
);
CREATE TABLE IF NOT EXISTS usuario (
  id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL,
  login TEXT NOT NULL UNIQUE,
  clave_hash TEXT NOT NULL,
  rol TEXT NOT NULL CHECK (rol IN ('ADMIN','CAJERO')),
  activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1))
);
CREATE TABLE IF NOT EXISTS compra (
  id_compra INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  id_proveedor INTEGER NOT NULL REFERENCES proveedor(id_proveedor),
  id_usuario INTEGER NOT NULL REFERENCES usuario(id_usuario),
  total REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS detalle_compra (
  id_detalle_compra INTEGER PRIMARY KEY AUTOINCREMENT,
  id_compra INTEGER NOT NULL REFERENCES compra(id_compra) ON DELETE CASCADE,
  id_producto INTEGER NOT NULL REFERENCES producto(id_producto),
  cantidad REAL NOT NULL CHECK (cantidad > 0),
  costo_unitario REAL NOT NULL CHECK (costo_unitario >= 0)
);
CREATE TABLE IF NOT EXISTS venta (
  id_venta INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  id_cliente INTEGER REFERENCES cliente(id_cliente),
  id_usuario INTEGER NOT NULL REFERENCES usuario(id_usuario),
  metodo_pago TEXT NOT NULL DEFAULT 'Efectivo'
     CHECK (metodo_pago IN ('Efectivo','Punto de venta','Pago móvil','Transferencia','Divisas')),
  total REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS detalle_venta (
  id_detalle_venta INTEGER PRIMARY KEY AUTOINCREMENT,
  id_venta INTEGER NOT NULL REFERENCES venta(id_venta) ON DELETE CASCADE,
  id_producto INTEGER NOT NULL REFERENCES producto(id_producto),
  cantidad REAL NOT NULL CHECK (cantidad > 0),
  precio_unitario REAL NOT NULL CHECK (precio_unitario >= 0)
);
CREATE TABLE IF NOT EXISTS movimiento_inventario (
  id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  id_producto INTEGER NOT NULL REFERENCES producto(id_producto),
  id_usuario INTEGER NOT NULL REFERENCES usuario(id_usuario),
  tipo TEXT NOT NULL CHECK (tipo IN ('ENTRADA','SALIDA','AJUSTE')),
  cantidad REAL NOT NULL CHECK (cantidad <> 0),
  referencia TEXT
);
CREATE INDEX IF NOT EXISTS ix_venta_fecha ON venta(fecha);
CREATE INDEX IF NOT EXISTS ix_mov_producto ON movimiento_inventario(id_producto);

-- Disparadores: actualizan existencias y registran el movimiento automáticamente
CREATE TRIGGER IF NOT EXISTS trg_salida_venta AFTER INSERT ON detalle_venta
BEGIN
  UPDATE producto SET stock_actual = stock_actual - NEW.cantidad WHERE id_producto = NEW.id_producto;
  INSERT INTO movimiento_inventario (id_producto, id_usuario, tipo, cantidad, referencia)
    SELECT NEW.id_producto, v.id_usuario, 'SALIDA', NEW.cantidad, 'VENTA-' || NEW.id_venta
      FROM venta v WHERE v.id_venta = NEW.id_venta;
END;
CREATE TRIGGER IF NOT EXISTS trg_entrada_compra AFTER INSERT ON detalle_compra
BEGIN
  UPDATE producto SET stock_actual = stock_actual + NEW.cantidad, costo = NEW.costo_unitario
   WHERE id_producto = NEW.id_producto;
  INSERT INTO movimiento_inventario (id_producto, id_usuario, tipo, cantidad, referencia)
    SELECT NEW.id_producto, c.id_usuario, 'ENTRADA', NEW.cantidad, 'COMPRA-' || NEW.id_compra
      FROM compra c WHERE c.id_compra = NEW.id_compra;
END;

-- Vistas para reportes
CREATE VIEW IF NOT EXISTS v_stock_bajo AS
  SELECT id_producto, codigo, nombre, tipo, unidad_medida, stock_actual, stock_minimo
    FROM producto WHERE activo = 1 AND stock_actual <= stock_minimo;
CREATE VIEW IF NOT EXISTS v_ventas_diarias AS
  SELECT date(fecha) AS dia, COUNT(*) AS nro_ventas, SUM(total) AS total
    FROM venta GROUP BY date(fecha);
CREATE VIEW IF NOT EXISTS v_productos_mas_vendidos AS
  SELECT p.id_producto, p.nombre, SUM(dv.cantidad) AS unidades,
         SUM(dv.cantidad * dv.precio_unitario) AS monto
    FROM detalle_venta dv JOIN producto p ON p.id_producto = dv.id_producto
   GROUP BY p.id_producto, p.nombre;
