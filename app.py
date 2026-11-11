"""Sistema Automatizado de Control de Inventarios y Gestión de Ventas
Compañía M&S, C.A. - Ciudad Ojeda, Estado Zulia
Ejecutar:  python app.py          (luego abrir http://127.0.0.1:5000)
           python app.py --demo   (carga datos de ejemplo la primera vez)
"""
import os, sys, io, secrets, sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, flash, abort, send_file)
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('MS_DB', os.path.join(BASE, 'data', 'sistema_ms.db'))
app = Flask(__name__)
KEY_FILE = os.path.join(BASE, 'data', '.secret_key')

def _secret():
    os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
    if not os.path.exists(KEY_FILE):
        with open(KEY_FILE, 'w') as f: f.write(secrets.token_hex(32))
    return open(KEY_FILE).read().strip()
app.secret_key = os.environ.get('MS_SECRET') or _secret()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')

METODOS = ['Efectivo', 'Punto de venta', 'Pago móvil', 'Transferencia', 'Divisas']

# ---------------------------------------------------------------- base de datos
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db

@app.teardown_appcontext
def close_db(_):
    db = g.pop('db', None)
    if db is not None: db.close()

def init_db(demo=False):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    with open(os.path.join(BASE, 'database', 'schema_sqlite.sql'), encoding='utf8') as f:
        db.executescript(f.read())
    if db.execute('SELECT COUNT(*) FROM usuario').fetchone()[0] == 0:
        db.execute("INSERT INTO usuario (nombre, login, clave_hash, rol) VALUES (?,?,?,?)",
                   ('Administrador', 'admin', generate_password_hash('admin123'), 'ADMIN'))
        for c in ['Empanadas', 'Arepas', 'Bebidas', 'Insumos']:
            db.execute('INSERT OR IGNORE INTO categoria (nombre) VALUES (?)', (c,))
        if demo: cargar_demo(db)
        db.commit()
    db.close()

def cargar_demo(db):
    db.execute("INSERT INTO usuario (nombre, login, clave_hash, rol) VALUES (?,?,?,?)",
               ('Cajero de prueba', 'cajero', generate_password_hash('cajero123'), 'CAJERO'))
    cat = {r[1]: r[0] for r in db.execute('SELECT id_categoria, nombre FROM categoria')}
    prods = [
        ('EMP-001', 'Empanada de queso', 'Empanadas', 'PRODUCTO', 'unidad', 2.0, 0.8, 0, 20),
        ('EMP-002', 'Empanada de carne mechada', 'Empanadas', 'PRODUCTO', 'unidad', 2.5, 1.1, 0, 20),
        ('EMP-003', 'Empanada de pollo', 'Empanadas', 'PRODUCTO', 'unidad', 2.5, 1.0, 0, 15),
        ('ARE-001', 'Arepa de queso', 'Arepas', 'PRODUCTO', 'unidad', 3.0, 1.2, 0, 10),
        ('ARE-002', 'Arepa reina pepiada', 'Arepas', 'PRODUCTO', 'unidad', 3.5, 1.5, 0, 10),
        ('BEB-001', 'Jugo natural', 'Bebidas', 'PRODUCTO', 'vaso', 1.5, 0.6, 0, 10),
        ('BEB-002', 'Café', 'Bebidas', 'PRODUCTO', 'taza', 1.0, 0.3, 0, 10),
        ('INS-001', 'Harina de maíz precocida', 'Insumos', 'INSUMO', 'kg', 0, 1.4, 0, 8),
        ('INS-002', 'Queso blanco duro', 'Insumos', 'INSUMO', 'kg', 0, 5.2, 0, 5),
    ]
    for c, n, ca, t, u, pv, co, st, sm in prods:
        db.execute('''INSERT INTO producto (codigo,nombre,id_categoria,tipo,unidad_medida,precio_venta,costo,stock_actual,stock_minimo)
                      VALUES (?,?,?,?,?,?,?,?,?)''', (c, n, cat[ca], t, u, pv, co, st, sm))
    db.execute("INSERT INTO proveedor (nombre,rif,telefono,direccion) VALUES ('Distribuidora El Zuliano, C.A.','J-30123456-7','0414-0000000','Ciudad Ojeda')")
    db.execute("INSERT INTO cliente (nombre,cedula_rif,telefono) VALUES ('Cliente de ejemplo','V-12345678','0414-1111111')")
    ids = {r['codigo']: r['id_producto'] for r in db.execute('SELECT id_producto, codigo FROM producto')}
    # compra inicial
    db.execute("INSERT INTO compra (fecha,id_proveedor,id_usuario) VALUES (?,1,1)", ((datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d 07:00:00'),))
    tot = 0
    for cod, q, cu in [('EMP-001', 60, .8), ('EMP-002', 50, 1.1), ('EMP-003', 40, 1.0), ('ARE-001', 30, 1.2),
                       ('ARE-002', 30, 1.5), ('BEB-001', 25, .6), ('BEB-002', 40, .3), ('INS-001', 12, 1.4), ('INS-002', 9, 5.2)]:
        db.execute('INSERT INTO detalle_compra (id_compra,id_producto,cantidad,costo_unitario) VALUES (1,?,?,?)', (ids[cod], q, cu)); tot += q * cu
    db.execute('UPDATE compra SET total=? WHERE id_compra=1', (round(tot, 2),))
    # ventas de ejemplo
    ventas = [(1, [('EMP-001', 12), ('BEB-001', 3)], 'Efectivo'), (1, [('ARE-001', 4), ('BEB-002', 4)], 'Pago móvil'),
              (0, [('EMP-002', 35), ('EMP-001', 30)], 'Punto de venta')]
    for k, (dias, items, mp) in enumerate(ventas):
        fecha = (datetime.now() - timedelta(days=1 if k < 2 else 0)).strftime('%Y-%m-%d') + ' 09:%02d:00' % (10 + k)
        cur = db.execute('INSERT INTO venta (fecha,id_cliente,id_usuario,metodo_pago) VALUES (?,?,?,?)', (fecha, 1 if k == 0 else None, 2, mp))
        vid = cur.lastrowid; total = 0
        for cod, q in items:
            pr = db.execute('SELECT precio_venta FROM producto WHERE id_producto=?', (ids[cod],)).fetchone()[0]
            db.execute('INSERT INTO detalle_venta (id_venta,id_producto,cantidad,precio_unitario) VALUES (?,?,?,?)', (vid, ids[cod], q, pr)); total += q * pr
        db.execute('UPDATE venta SET total=? WHERE id_venta=?', (round(total, 2), vid))

# ---------------------------------------------------------------- seguridad
@app.before_request
def cargar_usuario():
    g.user = None
    uid = session.get('uid')
    if uid:
        g.user = get_db().execute('SELECT * FROM usuario WHERE id_usuario=? AND activo=1', (uid,)).fetchone()
        if g.user is None: session.clear()
    if request.method == 'POST':
        tok = session.get('csrf')
        if not tok or tok != request.form.get('csrf'):
            abort(400, 'Solicitud no válida (token de seguridad).')

@app.context_processor
def inyectar():
    if 'csrf' not in session: session['csrf'] = secrets.token_hex(16)
    return dict(csrf=session['csrf'], user=g.get('user'), METODOS=METODOS)

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if g.user is None: return redirect(url_for('login', next=request.path))
        return f(*a, **k)
    return w

def admin_required(f):
    @wraps(f)
    @login_required
    def w(*a, **k):
        if g.user['rol'] != 'ADMIN':
            flash('No tiene permisos para acceder a esa sección.', 'error')
            return redirect(url_for('inicio'))
        return f(*a, **k)
    return w

@app.template_filter('money')
def money(v): return '${:,.2f}'.format(v or 0)
@app.template_filter('qty')
def qty(v):
    v = v or 0
    return ('%d' % v) if float(v).is_integer() else ('%.2f' % v)

def num(s, default=None):
    try: return float(str(s).replace(',', '.'))
    except (TypeError, ValueError): return default

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = get_db().execute('SELECT * FROM usuario WHERE login=? AND activo=1', (request.form.get('login', '').strip(),)).fetchone()
        if u and check_password_hash(u['clave_hash'], request.form.get('clave', '')):
            csrf = secrets.token_hex(16); session.clear(); session['uid'] = u['id_usuario']; session['csrf'] = csrf
            nxt = request.args.get('next') or ''
            return redirect(nxt if nxt.startswith('/') and not nxt.startswith('//') else url_for('inicio'))
        flash('Usuario o contraseña incorrectos.', 'error')
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.clear(); return redirect(url_for('login'))

# ---------------------------------------------------------------- inicio
@app.route('/')
@login_required
def inicio():
    db = get_db(); hoy = datetime.now().strftime('%Y-%m-%d')
    v = db.execute('SELECT COUNT(*) n, COALESCE(SUM(total),0) t FROM venta WHERE date(fecha)=?', (hoy,)).fetchone()
    bajos = db.execute('SELECT * FROM v_stock_bajo ORDER BY nombre').fetchall()
    nprod = db.execute('SELECT COUNT(*) FROM producto WHERE activo=1').fetchone()[0]
    ult = db.execute('''SELECT v.*, u.nombre usuario FROM venta v JOIN usuario u ON u.id_usuario=v.id_usuario
                        ORDER BY v.id_venta DESC LIMIT 6''').fetchall()
    sem = db.execute('SELECT dia, nro_ventas, total FROM v_ventas_diarias WHERE dia >= ? ORDER BY dia',
                     ((datetime.now() - timedelta(days=6)).strftime('%Y-%m-%d'),)).fetchall()
    return render_template('inicio.html', v=v, bajos=bajos, nprod=nprod, ult=ult, sem=sem)

# ---------------------------------------------------------------- categorías
@app.route('/categorias', methods=['GET', 'POST'])
@admin_required
def categorias():
    db = get_db()
    if request.method == 'POST':
        n = request.form.get('nombre', '').strip()
        if not n: flash('Escriba el nombre de la categoría.', 'error')
        else:
            try: db.execute('INSERT INTO categoria (nombre) VALUES (?)', (n,)); db.commit(); flash('Categoría creada.', 'ok')
            except sqlite3.IntegrityError: flash('Esa categoría ya existe.', 'error')
        return redirect(url_for('categorias'))
    rows = db.execute('''SELECT c.*, (SELECT COUNT(*) FROM producto p WHERE p.id_categoria=c.id_categoria) n
                         FROM categoria c ORDER BY nombre''').fetchall()
    return render_template('categorias.html', rows=rows)

# ---------------------------------------------------------------- productos
@app.route('/productos')
@login_required
def productos():
    q = request.args.get('q', '').strip(); tipo = request.args.get('tipo', ''); solo_bajo = request.args.get('bajo') == '1'
    sql = '''SELECT p.*, c.nombre categoria FROM producto p JOIN categoria c ON c.id_categoria=p.id_categoria WHERE 1=1'''; a = []
    if q: sql += ' AND (p.nombre LIKE ? OR p.codigo LIKE ?)'; a += [f'%{q}%'] * 2
    if tipo in ('PRODUCTO', 'INSUMO'): sql += ' AND p.tipo=?'; a.append(tipo)
    if solo_bajo: sql += ' AND p.activo=1 AND p.stock_actual <= p.stock_minimo'
    rows = get_db().execute(sql + ' ORDER BY p.activo DESC, p.nombre', a).fetchall()
    return render_template('productos.html', rows=rows, q=q, tipo=tipo, bajo=solo_bajo)

def _form_producto(db, pid=None):
    f = request.form
    d = dict(codigo=f.get('codigo', '').strip().upper(), nombre=f.get('nombre', '').strip(), id_categoria=f.get('id_categoria'),
             tipo=f.get('tipo'), unidad_medida=f.get('unidad_medida', '').strip(), precio_venta=num(f.get('precio_venta'), 0),
             costo=num(f.get('costo'), 0), stock_minimo=num(f.get('stock_minimo'), 0))
    if not d['codigo'] or not d['nombre'] or not d['unidad_medida'] or d['tipo'] not in ('PRODUCTO', 'INSUMO') or not d['id_categoria']:
        flash('Complete todos los campos obligatorios.', 'error'); return None
    if min(d['precio_venta'], d['costo'], d['stock_minimo']) < 0:
        flash('Los valores numéricos no pueden ser negativos.', 'error'); return None
    return d

@app.route('/productos/nuevo', methods=['GET', 'POST'])
@admin_required
def producto_nuevo():
    db = get_db(); cats = db.execute('SELECT * FROM categoria ORDER BY nombre').fetchall()
    if request.method == 'POST':
        d = _form_producto(db)
        if d:
            stock = num(request.form.get('stock_inicial'), 0)
            if stock < 0: flash('La existencia inicial no puede ser negativa.', 'error')
            else:
                try:
                    cur = db.execute('''INSERT INTO producto (codigo,nombre,id_categoria,tipo,unidad_medida,precio_venta,costo,stock_minimo)
                        VALUES (:codigo,:nombre,:id_categoria,:tipo,:unidad_medida,:precio_venta,:costo,:stock_minimo)''', d)
                    if stock > 0:
                        db.execute('UPDATE producto SET stock_actual=? WHERE id_producto=?', (stock, cur.lastrowid))
                        db.execute("INSERT INTO movimiento_inventario (id_producto,id_usuario,tipo,cantidad,referencia) VALUES (?,?,'AJUSTE',?,'EXISTENCIA INICIAL')",
                                   (cur.lastrowid, g.user['id_usuario'], stock))
                    db.commit(); flash('Producto registrado.', 'ok'); return redirect(url_for('productos'))
                except sqlite3.IntegrityError: db.rollback(); flash('Ya existe un producto con ese código.', 'error')
    return render_template('producto_form.html', p=request.form if request.method == 'POST' else {}, cats=cats, nuevo=True)

@app.route('/productos/<int:pid>/editar', methods=['GET', 'POST'])
@admin_required
def producto_editar(pid):
    db = get_db(); p = db.execute('SELECT * FROM producto WHERE id_producto=?', (pid,)).fetchone() or abort(404)
    cats = db.execute('SELECT * FROM categoria ORDER BY nombre').fetchall()
    if request.method == 'POST':
        d = _form_producto(db, pid)
        if d:
            d['id'] = pid
            try:
                db.execute('''UPDATE producto SET codigo=:codigo,nombre=:nombre,id_categoria=:id_categoria,tipo=:tipo,
                              unidad_medida=:unidad_medida,precio_venta=:precio_venta,costo=:costo,stock_minimo=:stock_minimo
                              WHERE id_producto=:id''', d)
                db.commit(); flash('Producto actualizado.', 'ok'); return redirect(url_for('productos'))
            except sqlite3.IntegrityError: db.rollback(); flash('Ya existe un producto con ese código.', 'error')
        p = request.form
    return render_template('producto_form.html', p=p, cats=cats, nuevo=False, pid=pid)

@app.route('/productos/<int:pid>/estado', methods=['POST'])
@admin_required
def producto_estado(pid):
    db = get_db(); db.execute('UPDATE producto SET activo = 1 - activo WHERE id_producto=?', (pid,)); db.commit()
    flash('Estado del producto actualizado.', 'ok'); return redirect(url_for('productos'))

@app.route('/productos/<int:pid>/ajuste', methods=['GET', 'POST'])
@admin_required
def producto_ajuste(pid):
    db = get_db(); p = db.execute('SELECT * FROM producto WHERE id_producto=?', (pid,)).fetchone() or abort(404)
    if request.method == 'POST':
        nuevo = num(request.form.get('nuevo_stock')); motivo = request.form.get('motivo', '').strip()
        if nuevo is None or nuevo < 0 or not motivo: flash('Indique una existencia válida y el motivo del ajuste.', 'error')
        else:
            delta = round(nuevo - p['stock_actual'], 4)
            if delta == 0: flash('La existencia indicada es igual a la actual.', 'error')
            else:
                db.execute('UPDATE producto SET stock_actual=? WHERE id_producto=?', (nuevo, pid))
                db.execute("INSERT INTO movimiento_inventario (id_producto,id_usuario,tipo,cantidad,referencia) VALUES (?,?,'AJUSTE',?,?)",
                           (pid, g.user['id_usuario'], delta, 'AJUSTE: ' + motivo[:30]))
                db.commit(); flash('Existencia ajustada.', 'ok'); return redirect(url_for('productos'))
    return render_template('ajuste.html', p=p)

# ---------------------------------------------------------------- proveedores y clientes
@app.route('/proveedores', methods=['GET', 'POST'])
@admin_required
def proveedores():
    db = get_db()
    if request.method == 'POST':
        f = request.form; n = f.get('nombre', '').strip()
        if not n: flash('Escriba el nombre del proveedor.', 'error')
        else:
            try:
                db.execute('INSERT INTO proveedor (nombre,rif,telefono,direccion) VALUES (?,?,?,?)',
                           (n, f.get('rif', '').strip().upper() or None, f.get('telefono', '').strip(), f.get('direccion', '').strip()))
                db.commit(); flash('Proveedor registrado.', 'ok')
            except sqlite3.IntegrityError: flash('Ya existe un proveedor con ese RIF.', 'error')
        return redirect(url_for('proveedores'))
    return render_template('proveedores.html', rows=db.execute('SELECT * FROM proveedor ORDER BY nombre').fetchall())

@app.route('/clientes', methods=['GET', 'POST'])
@login_required
def clientes():
    db = get_db()
    if request.method == 'POST':
        f = request.form; n = f.get('nombre', '').strip()
        if not n: flash('Escriba el nombre del cliente.', 'error')
        else:
            try:
                db.execute('INSERT INTO cliente (nombre,cedula_rif,telefono) VALUES (?,?,?)',
                           (n, f.get('cedula_rif', '').strip().upper() or None, f.get('telefono', '').strip()))
                db.commit(); flash('Cliente registrado.', 'ok')
            except sqlite3.IntegrityError: flash('Ya existe un cliente con esa cédula/RIF.', 'error')
        return redirect(url_for('clientes'))
    return render_template('clientes.html', rows=db.execute('SELECT * FROM cliente ORDER BY nombre').fetchall())

# ---------------------------------------------------------------- ventas
def _parse_items(db, con_precio_bd=True):
    ids = request.form.getlist('id_producto'); cants = request.form.getlist('cantidad'); costos = request.form.getlist('costo')
    agr = {}
    for i, (pid, c) in enumerate(zip(ids, cants)):
        if not pid: continue
        c = num(c)
        if c is None or c <= 0: return None, 'Todas las cantidades deben ser mayores que cero.'
        costo = num(costos[i]) if i < len(costos) else None
        a = agr.setdefault(int(pid), {'cant': 0, 'costo': costo}); a['cant'] += c
        if costo is not None: a['costo'] = costo
    if not agr: return None, 'Agregue al menos un producto.'
    return agr, None

@app.route('/ventas')
@login_required
def ventas():
    desde = request.args.get('desde', ''); hasta = request.args.get('hasta', '')
    sql = '''SELECT v.*, u.nombre usuario, c.nombre cliente FROM venta v JOIN usuario u ON u.id_usuario=v.id_usuario
             LEFT JOIN cliente c ON c.id_cliente=v.id_cliente WHERE 1=1'''; a = []
    if desde: sql += ' AND date(v.fecha) >= ?'; a.append(desde)
    if hasta: sql += ' AND date(v.fecha) <= ?'; a.append(hasta)
    if g.user['rol'] != 'ADMIN': sql += ' AND v.id_usuario = ?'; a.append(g.user['id_usuario'])
    rows = get_db().execute(sql + ' ORDER BY v.id_venta DESC LIMIT 300', a).fetchall()
    return render_template('ventas.html', rows=rows, desde=desde, hasta=hasta, total=sum(r['total'] for r in rows))

@app.route('/ventas/nueva', methods=['GET', 'POST'])
@login_required
def venta_nueva():
    db = get_db()
    prods = db.execute("SELECT * FROM producto WHERE activo=1 AND tipo='PRODUCTO' ORDER BY nombre").fetchall()
    clientes_ = db.execute('SELECT * FROM cliente ORDER BY nombre').fetchall()
    if request.method == 'POST':
        items, err = _parse_items(db)
        mp = request.form.get('metodo_pago'); cli = request.form.get('id_cliente') or None
        if not err and mp not in METODOS: err = 'Seleccione el método de pago.'
        if not err:
            filas = []
            for pid, it in items.items():
                p = db.execute("SELECT * FROM producto WHERE id_producto=? AND activo=1 AND tipo='PRODUCTO'", (pid,)).fetchone()
                if not p: err = 'Hay un producto no disponible para la venta.'; break
                if it['cant'] > p['stock_actual']:
                    err = f"Existencias insuficientes de {p['nombre']} (disponible: {qty(p['stock_actual'])})."; break
                filas.append((pid, it['cant'], p['precio_venta']))
        if err: flash(err, 'error')
        else:
            try:
                cur = db.execute('INSERT INTO venta (id_cliente,id_usuario,metodo_pago) VALUES (?,?,?)', (cli, g.user['id_usuario'], mp))
                vid = cur.lastrowid; total = 0
                for pid, c, pr in filas:
                    db.execute('INSERT INTO detalle_venta (id_venta,id_producto,cantidad,precio_unitario) VALUES (?,?,?,?)', (vid, pid, c, pr)); total += c * pr
                db.execute('UPDATE venta SET total=? WHERE id_venta=?', (round(total, 2), vid)); db.commit()
                flash(f'Venta #{vid} registrada por {money(total)}.', 'ok'); return redirect(url_for('venta_detalle', vid=vid))
            except sqlite3.IntegrityError:
                db.rollback(); flash('No se pudo registrar la venta: existencias insuficientes.', 'error')
    return render_template('venta_nueva.html', prods=prods, clientes=clientes_)

@app.route('/ventas/<int:vid>')
@login_required
def venta_detalle(vid):
    db = get_db()
    v = db.execute('''SELECT v.*, u.nombre usuario, c.nombre cliente FROM venta v JOIN usuario u ON u.id_usuario=v.id_usuario
                      LEFT JOIN cliente c ON c.id_cliente=v.id_cliente WHERE v.id_venta=?''', (vid,)).fetchone() or abort(404)
    if g.user['rol'] != 'ADMIN' and v['id_usuario'] != g.user['id_usuario']: abort(403)
    det = db.execute('''SELECT d.*, p.nombre, p.codigo FROM detalle_venta d JOIN producto p ON p.id_producto=d.id_producto
                        WHERE d.id_venta=?''', (vid,)).fetchall()
    return render_template('venta_detalle.html', v=v, det=det)

# ---------------------------------------------------------------- compras
@app.route('/compras')
@admin_required
def compras():
    rows = get_db().execute('''SELECT c.*, p.nombre proveedor, u.nombre usuario FROM compra c
        JOIN proveedor p ON p.id_proveedor=c.id_proveedor JOIN usuario u ON u.id_usuario=c.id_usuario
        ORDER BY c.id_compra DESC LIMIT 300''').fetchall()
    return render_template('compras.html', rows=rows)

@app.route('/compras/nueva', methods=['GET', 'POST'])
@admin_required
def compra_nueva():
    db = get_db()
    prods = db.execute('SELECT * FROM producto WHERE activo=1 ORDER BY tipo DESC, nombre').fetchall()
    provs = db.execute('SELECT * FROM proveedor ORDER BY nombre').fetchall()
    if request.method == 'POST':
        items, err = _parse_items(db); prov = request.form.get('id_proveedor')
        if not err and not prov: err = 'Seleccione el proveedor.'
        if not err:
            for pid, it in items.items():
                if it['costo'] is None or it['costo'] < 0: err = 'Indique un costo unitario válido para cada producto.'; break
        if err: flash(err, 'error')
        else:
            try:
                cur = db.execute('INSERT INTO compra (id_proveedor,id_usuario) VALUES (?,?)', (prov, g.user['id_usuario']))
                cid = cur.lastrowid; total = 0
                for pid, it in items.items():
                    db.execute('INSERT INTO detalle_compra (id_compra,id_producto,cantidad,costo_unitario) VALUES (?,?,?,?)', (cid, pid, it['cant'], it['costo']))
                    total += it['cant'] * it['costo']
                db.execute('UPDATE compra SET total=? WHERE id_compra=?', (round(total, 2), cid)); db.commit()
                flash(f'Compra #{cid} registrada: las existencias fueron actualizadas.', 'ok'); return redirect(url_for('compra_detalle', cid=cid))
            except sqlite3.IntegrityError: db.rollback(); flash('No se pudo registrar la compra.', 'error')
    return render_template('compra_nueva.html', prods=prods, provs=provs)

@app.route('/compras/<int:cid>')
@admin_required
def compra_detalle(cid):
    db = get_db()
    c = db.execute('''SELECT c.*, p.nombre proveedor, u.nombre usuario FROM compra c JOIN proveedor p ON p.id_proveedor=c.id_proveedor
                      JOIN usuario u ON u.id_usuario=c.id_usuario WHERE c.id_compra=?''', (cid,)).fetchone() or abort(404)
    det = db.execute('''SELECT d.*, p.nombre, p.codigo FROM detalle_compra d JOIN producto p ON p.id_producto=d.id_producto
                        WHERE d.id_compra=?''', (cid,)).fetchall()
    return render_template('compra_detalle.html', c=c, det=det)

# ---------------------------------------------------------------- movimientos y reportes
@app.route('/movimientos')
@admin_required
def movimientos():
    pid = request.args.get('producto', '')
    sql = '''SELECT m.*, p.nombre producto, p.codigo, u.nombre usuario FROM movimiento_inventario m
             JOIN producto p ON p.id_producto=m.id_producto JOIN usuario u ON u.id_usuario=m.id_usuario'''; a = []
    if pid.isdigit(): sql += ' WHERE m.id_producto=?'; a.append(int(pid))
    db = get_db()
    return render_template('movimientos.html', rows=db.execute(sql + ' ORDER BY m.id_movimiento DESC LIMIT 400', a).fetchall(),
                           prods=db.execute('SELECT id_producto, nombre FROM producto ORDER BY nombre').fetchall(), pid=pid)

@app.route('/reportes')
@admin_required
def reportes():
    db = get_db(); hoy = datetime.now()
    desde = request.args.get('desde') or (hoy - timedelta(days=29)).strftime('%Y-%m-%d'); hasta = request.args.get('hasta') or hoy.strftime('%Y-%m-%d')
    diarias = db.execute('SELECT * FROM v_ventas_diarias WHERE dia BETWEEN ? AND ? ORDER BY dia DESC', (desde, hasta)).fetchall()
    top = db.execute('''SELECT p.nombre, SUM(dv.cantidad) unidades, SUM(dv.cantidad*dv.precio_unitario) monto
        FROM detalle_venta dv JOIN venta v ON v.id_venta=dv.id_venta JOIN producto p ON p.id_producto=dv.id_producto
        WHERE date(v.fecha) BETWEEN ? AND ? GROUP BY p.id_producto, p.nombre ORDER BY unidades DESC LIMIT 15''', (desde, hasta)).fetchall()
    pagos = db.execute('SELECT metodo_pago, COUNT(*) n, SUM(total) t FROM venta WHERE date(fecha) BETWEEN ? AND ? GROUP BY metodo_pago ORDER BY t DESC', (desde, hasta)).fetchall()
    bajos = db.execute('SELECT * FROM v_stock_bajo ORDER BY nombre').fetchall()
    valor = db.execute('SELECT COALESCE(SUM(stock_actual*costo),0) FROM producto WHERE activo=1').fetchone()[0]
    return render_template('reportes.html', desde=desde, hasta=hasta, diarias=diarias, top=top, pagos=pagos, bajos=bajos,
                           valor=valor, total=sum(d['total'] for d in diarias))

@app.route('/reportes/inventario.xlsx')
@admin_required
def inventario_xlsx():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook(); ws = wb.active; ws.title = 'Inventario'
    ws.append(['Código', 'Producto', 'Categoría', 'Tipo', 'Unidad', 'Existencia', 'Mínimo', 'Costo (USD)', 'Precio venta (USD)', 'Valor en inventario (USD)'])
    for c in ws[1]: c.font = Font(bold=True, color='FFFFFF'); c.fill = PatternFill('solid', fgColor='1F3864')
    for r in get_db().execute('''SELECT p.*, c.nombre cat FROM producto p JOIN categoria c ON c.id_categoria=p.id_categoria
                                 WHERE p.activo=1 ORDER BY p.nombre'''):
        ws.append([r['codigo'], r['nombre'], r['cat'], r['tipo'], r['unidad_medida'], r['stock_actual'], r['stock_minimo'],
                   r['costo'], r['precio_venta'], round(r['stock_actual'] * r['costo'], 2)])
    for col, w in zip('ABCDEFGHIJ', [11, 30, 14, 11, 10, 11, 9, 12, 16, 22]): ws.column_dimensions[col].width = w
    bio = io.BytesIO(); wb.save(bio); bio.seek(0)
    return send_file(bio, as_attachment=True, download_name='inventario_%s.xlsx' % datetime.now().strftime('%Y%m%d'),
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# ---------------------------------------------------------------- usuarios
@app.route('/usuarios', methods=['GET', 'POST'])
@admin_required
def usuarios():
    db = get_db()
    if request.method == 'POST':
        f = request.form; n = f.get('nombre', '').strip(); lg = f.get('login', '').strip().lower(); cl = f.get('clave', ''); rol = f.get('rol')
        if not n or not lg or rol not in ('ADMIN', 'CAJERO'): flash('Complete todos los campos.', 'error')
        elif len(cl) < 6: flash('La contraseña debe tener al menos 6 caracteres.', 'error')
        else:
            try:
                db.execute('INSERT INTO usuario (nombre,login,clave_hash,rol) VALUES (?,?,?,?)', (n, lg, generate_password_hash(cl), rol))
                db.commit(); flash('Usuario creado.', 'ok')
            except sqlite3.IntegrityError: flash('Ese nombre de usuario ya existe.', 'error')
        return redirect(url_for('usuarios'))
    return render_template('usuarios.html', rows=db.execute('SELECT * FROM usuario ORDER BY nombre').fetchall())

@app.route('/usuarios/<int:uid>/estado', methods=['POST'])
@admin_required
def usuario_estado(uid):
    if uid == g.user['id_usuario']: flash('No puede desactivar su propio usuario.', 'error')
    else:
        db = get_db(); db.execute('UPDATE usuario SET activo = 1 - activo WHERE id_usuario=?', (uid,)); db.commit(); flash('Usuario actualizado.', 'ok')
    return redirect(url_for('usuarios'))

@app.route('/usuarios/<int:uid>/clave', methods=['POST'])
@admin_required
def usuario_clave(uid):
    cl = request.form.get('clave', '')
    if len(cl) < 6: flash('La contraseña debe tener al menos 6 caracteres.', 'error')
    else:
        db = get_db(); db.execute('UPDATE usuario SET clave_hash=? WHERE id_usuario=?', (generate_password_hash(cl), uid)); db.commit(); flash('Contraseña restablecida.', 'ok')
    return redirect(url_for('usuarios'))

@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    if request.method == 'POST':
        act, nueva = request.form.get('actual', ''), request.form.get('nueva', '')
        if not check_password_hash(g.user['clave_hash'], act): flash('La contraseña actual es incorrecta.', 'error')
        elif len(nueva) < 6: flash('La nueva contraseña debe tener al menos 6 caracteres.', 'error')
        else:
            db = get_db(); db.execute('UPDATE usuario SET clave_hash=? WHERE id_usuario=?', (generate_password_hash(nueva), g.user['id_usuario'])); db.commit()
            flash('Contraseña actualizada.', 'ok'); return redirect(url_for('inicio'))
    return render_template('perfil.html')

@app.route('/respaldo', methods=['POST'])
@admin_required
def respaldo():
    """Genera una copia de seguridad de la base de datos y la descarga."""
    src = get_db(); bio = io.BytesIO(); tmp = os.path.join(BASE, 'data', '_respaldo.tmp')
    dst = sqlite3.connect(tmp); src.backup(dst); dst.close()
    with open(tmp, 'rb') as f: bio.write(f.read())
    os.remove(tmp); bio.seek(0)
    return send_file(bio, as_attachment=True, download_name='respaldo_ms_%s.db' % datetime.now().strftime('%Y%m%d_%H%M'),
                     mimetype='application/octet-stream')

init_db(demo='--demo' in sys.argv)
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
