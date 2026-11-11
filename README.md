# Sistema Automatizado de Control de Inventarios y Gestión de Ventas
**Compañía M&S, C.A. – Ciudad Ojeda, Estado Zulia** · Proyecto Socio Tecnológico · UNERMB

Sistema desarrollado según la propuesta del proyecto: base de datos relacional de 10 tablas (modelo
entidad-relación del informe), disparadores que actualizan las existencias, vistas para reportes,
roles de usuario y una aplicación web para usarlo en el día a día. Solo usa software libre.

## 1. Requisitos
- Python 3.9 o superior (https://www.python.org – marcar "Add Python to PATH" al instalar en Windows).
- Conexión a internet solo la primera vez, para instalar Flask y openpyxl.

## 2. Cómo iniciarlo
**Windows:** doble clic en `iniciar_demo.bat` (primera vez, con datos de ejemplo) o en `iniciar.bat`
(base de datos vacía). Se abre el navegador en http://127.0.0.1:5000.

**Linux / macOS:** `./iniciar.sh --demo` la primera vez; luego `./iniciar.sh`.

> La base de datos se crea sola en `data/sistema_ms.db`. Si quiere empezar de cero, cierre el sistema,
> borre ese archivo y vuelva a iniciarlo.

## 3. Usuarios iniciales
| Usuario | Contraseña   | Rol            |
|---------|--------------|----------------|
| admin   | admin123     | Administrador  |
| cajero  | cajero123    | Cajero (solo con `--demo`) |

**Cambie las contraseñas** en *Mi perfil* / *Usuarios* antes de usarlo con datos reales.

## 4. ¿Qué puede hacer cada rol?
- **Cajero:** registrar ventas, consultar inventario y existencias bajas, registrar clientes, ver sus propias ventas.
- **Administrador:** todo lo anterior más productos e insumos (crear, editar, ajustar existencias, activar/desactivar),
  categorías, proveedores, compras, historial de movimientos, reportes, exportar inventario a Excel,
  usuarios y respaldo de la base de datos.

## 5. Funciones principales (requerimientos RF-01 a RF-07 del informe)
| Req. | Función | Dónde |
|------|---------|-------|
| RF-01 | Registrar, modificar y desactivar productos e insumos | Inventario |
| RF-02 | Registrar compras; las existencias suben solas | Compras |
| RF-03 | Registrar ventas; las existencias bajan solas | Nueva venta |
| RF-04 | Alerta de existencias bajas (fila naranja) | Inicio, Inventario, Reportes |
| RF-05 | Historial de entradas, salidas y ajustes | Movimientos |
| RF-06 | Ventas diarias, más vendidos, por método de pago | Reportes |
| RF-07 | Usuarios y roles | Usuarios |

Reglas que protege el sistema: no se puede vender más de lo que hay (no hay existencias negativas),
el precio de venta lo toma siempre la base de datos, las contraseñas se guardan cifradas,
y cada compra/venta/ajuste deja un movimiento registrado.

## 6. Respaldo
En *Usuarios → Descargar respaldo* se obtiene una copia (`.db`) de toda la información.
Guárdela en una unidad externa a diario. Para restaurar: cierre el sistema y reemplace `data/sistema_ms.db` por la copia.

## 7. Estructura del proyecto
```
app.py                       Aplicación (rutas, reglas del negocio)
database/schema_sqlite.sql   Base de datos que usa la aplicación (tablas, triggers, vistas)
database/database_postgresql.sql  Mismo diseño para PostgreSQL (ver nota)
templates/ , static/         Pantallas y estilos
test_sistema.py              52 pruebas automáticas  (python test_sistema.py)
```

## 8. Nota sobre PostgreSQL
El informe menciona PostgreSQL. La aplicación incluida funciona con **SQLite** (viene con Python, sin instalar nada)
porque es lo más sencillo para un negocio con un solo equipo. El script `database/database_postgresql.sql`
contiene el mismo modelo (tablas, restricciones, triggers, vistas, roles `ms_admin`/`ms_cajero` y usuario inicial)
para quien desee montarlo en un servidor PostgreSQL 12+: `createdb sistema_ms` y
`psql -d sistema_ms -f database/database_postgresql.sql`. **Ese script no pudo ejecutarse en el entorno donde
se preparó el sistema**, por lo que conviene probarlo y, si el profesor exige PostgreSQL, conectar la aplicación a él.

## 9. Uso en red local (opcional)
Para que otras computadoras del local lo usen: `set MS_HOST=0.0.0.0` (Windows) o `MS_HOST=0.0.0.0 ./iniciar.sh`,
y abrir `http://IP-DEL-EQUIPO:5000`. Úselo solo dentro de la red del local; no lo exponga a internet.
