-- =====================================================================
-- Sistema Automatizado de Control de Inventarios y Gestión de Ventas
-- Compañía M&S, C.A. - Ciudad Ojeda, Estado Zulia
-- Script para PostgreSQL 12 o superior.
-- Uso:  createdb sistema_ms
--       psql -d sistema_ms -f database_postgresql.sql
-- =====================================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE categoria (
  id_categoria SERIAL PRIMARY KEY,
  nombre       VARCHAR(60) NOT NULL UNIQUE
);
CREATE TABLE producto (
  id_producto   SERIAL PRIMARY KEY,
  codigo        VARCHAR(20)  NOT NULL UNIQUE,
  nombre        VARCHAR(100) NOT NULL,
  id_categoria  INT NOT NULL REFERENCES categoria(id_categoria),
  tipo          VARCHAR(10) NOT NULL CHECK (tipo IN ('PRODUCTO','INSUMO')),
  unidad_medida VARCHAR(15) NOT NULL,
  precio_venta  NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (precio_venta >= 0),
  costo         NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (costo >= 0),
  stock_actual  NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (stock_actual >= 0),
  stock_minimo  NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
  activo        BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE proveedor (
  id_proveedor SERIAL PRIMARY KEY,
  nombre       VARCHAR(100) NOT NULL,
  rif          VARCHAR(20) UNIQUE,
  telefono     VARCHAR(30),
  direccion    VARCHAR(200)
);
CREATE TABLE cliente (
  id_cliente SERIAL PRIMARY KEY,
  nombre     VARCHAR(100) NOT NULL,
  cedula_rif VARCHAR(20) UNIQUE,
  telefono   VARCHAR(30)
);
CREATE TABLE usuario (
  id_usuario SERIAL PRIMARY KEY,
  nombre     VARCHAR(100) NOT NULL,
  login      VARCHAR(30)  NOT NULL UNIQUE,
  clave_hash TEXT NOT NULL,
  rol        VARCHAR(10) NOT NULL CHECK (rol IN ('ADMIN','CAJERO')),
  activo     BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE compra (
  id_compra    SERIAL PRIMARY KEY,
  fecha        TIMESTAMP NOT NULL DEFAULT NOW(),
  id_proveedor INT NOT NULL REFERENCES proveedor(id_proveedor),
  id_usuario   INT NOT NULL REFERENCES usuario(id_usuario),
  total        NUMERIC(12,2) NOT NULL DEFAULT 0
);
CREATE TABLE detalle_compra (
  id_detalle_compra SERIAL PRIMARY KEY,
  id_compra      INT NOT NULL REFERENCES compra(id_compra) ON DELETE CASCADE,
  id_producto    INT NOT NULL REFERENCES producto(id_producto),
  cantidad       NUMERIC(10,2) NOT NULL CHECK (cantidad > 0),
  costo_unitario NUMERIC(10,2) NOT NULL CHECK (costo_unitario >= 0)
);
CREATE TABLE venta (
  id_venta    SERIAL PRIMARY KEY,
  fecha       TIMESTAMP NOT NULL DEFAULT NOW(),
  id_cliente  INT REFERENCES cliente(id_cliente),
  id_usuario  INT NOT NULL REFERENCES usuario(id_usuario),
  metodo_pago VARCHAR(20) NOT NULL DEFAULT 'Efectivo'
     CHECK (metodo_pago IN ('Efectivo','Punto de venta','Pago móvil','Transferencia','Divisas')),
  total       NUMERIC(12,2) NOT NULL DEFAULT 0
);
CREATE TABLE detalle_venta (
  id_detalle_venta SERIAL PRIMARY KEY,
  id_venta        INT NOT NULL REFERENCES venta(id_venta) ON DELETE CASCADE,
  id_producto     INT NOT NULL REFERENCES producto(id_producto),
  cantidad        NUMERIC(10,2) NOT NULL CHECK (cantidad > 0),
  precio_unitario NUMERIC(10,2) NOT NULL CHECK (precio_unitario >= 0)
);
CREATE TABLE movimiento_inventario (
  id_movimiento SERIAL PRIMARY KEY,
  fecha         TIMESTAMP NOT NULL DEFAULT NOW(),
  id_producto   INT NOT NULL REFERENCES producto(id_producto),
  id_usuario    INT NOT NULL REFERENCES usuario(id_usuario),
  tipo          VARCHAR(10) NOT NULL CHECK (tipo IN ('ENTRADA','SALIDA','AJUSTE')),
  cantidad      NUMERIC(10,2) NOT NULL CHECK (cantidad <> 0),
  referencia    VARCHAR(40)
);
CREATE INDEX ix_venta_fecha ON venta(fecha);
CREATE INDEX ix_mov_producto ON movimiento_inventario(id_producto);

-- Disparadores -------------------------------------------------------
CREATE FUNCTION fn_salida_venta() RETURNS TRIGGER AS $$
BEGIN
  UPDATE producto SET stock_actual = stock_actual - NEW.cantidad
   WHERE id_producto = NEW.id_producto;
  INSERT INTO movimiento_inventario (id_producto, id_usuario, tipo, cantidad, referencia)
  SELECT NEW.id_producto, v.id_usuario, 'SALIDA', NEW.cantidad, 'VENTA-' || NEW.id_venta
    FROM venta v WHERE v.id_venta = NEW.id_venta;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_salida_venta AFTER INSERT ON detalle_venta
  FOR EACH ROW EXECUTE FUNCTION fn_salida_venta();

CREATE FUNCTION fn_entrada_compra() RETURNS TRIGGER AS $$
BEGIN
  UPDATE producto SET stock_actual = stock_actual + NEW.cantidad, costo = NEW.costo_unitario
   WHERE id_producto = NEW.id_producto;
  INSERT INTO movimiento_inventario (id_producto, id_usuario, tipo, cantidad, referencia)
  SELECT NEW.id_producto, c.id_usuario, 'ENTRADA', NEW.cantidad, 'COMPRA-' || NEW.id_compra
    FROM compra c WHERE c.id_compra = NEW.id_compra;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_entrada_compra AFTER INSERT ON detalle_compra
  FOR EACH ROW EXECUTE FUNCTION fn_entrada_compra();

-- Vistas para reportes -----------------------------------------------
CREATE VIEW v_stock_bajo AS
  SELECT id_producto, codigo, nombre, tipo, unidad_medida, stock_actual, stock_minimo
    FROM producto WHERE activo AND stock_actual <= stock_minimo;
CREATE VIEW v_ventas_diarias AS
  SELECT CAST(fecha AS DATE) AS dia, COUNT(*) AS nro_ventas, SUM(total) AS total
    FROM venta GROUP BY CAST(fecha AS DATE) ORDER BY dia;
CREATE VIEW v_productos_mas_vendidos AS
  SELECT p.id_producto, p.nombre, SUM(dv.cantidad) AS unidades,
         SUM(dv.cantidad * dv.precio_unitario) AS monto
    FROM detalle_venta dv JOIN producto p ON p.id_producto = dv.id_producto
   GROUP BY p.id_producto, p.nombre ORDER BY unidades DESC;

-- Roles de acceso ----------------------------------------------------
CREATE ROLE ms_admin  NOLOGIN;
CREATE ROLE ms_cajero NOLOGIN;
GRANT ALL ON ALL TABLES IN SCHEMA public TO ms_admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO ms_admin;
GRANT SELECT ON producto, categoria, cliente, v_stock_bajo TO ms_cajero;
GRANT SELECT, INSERT ON venta, detalle_venta, movimiento_inventario TO ms_cajero;
GRANT UPDATE (stock_actual) ON producto TO ms_cajero;
GRANT INSERT ON cliente TO ms_cajero;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO ms_cajero;
-- (Para usar los roles: CREATE USER maria LOGIN PASSWORD '...' IN ROLE ms_cajero;)

-- Datos iniciales ----------------------------------------------------
INSERT INTO categoria (nombre) VALUES ('Empanadas'),('Arepas'),('Bebidas'),('Insumos');
INSERT INTO usuario (nombre, login, clave_hash, rol)
VALUES ('Administrador', 'admin', crypt('admin123', gen_salt('bf')), 'ADMIN');
