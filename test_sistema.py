"""Pruebas automáticas del sistema. Ejecutar: python test_sistema.py"""
import os, sys, tempfile, re
tmp = tempfile.mkdtemp(); os.environ['MS_DB'] = os.path.join(tmp, 't.db'); sys.argv.append('--demo')
import app as A
c = A.app.test_client(); ok = 0
def check(nombre, cond):
    global ok
    print(('  OK  ' if cond else ' FALLA ') + nombre); ok += bool(cond)
    if not cond: sys.exit(1)
def tok(html): return re.search(r'name="csrf" value="([^"]+)"', html).group(1)
def post(url, data, follow=True):
    html = c.get('/').get_data(as_text=True) if False else None
    with c.session_transaction() as s: t = s.get('csrf')
    return c.post(url, data={**data, 'csrf': t}, follow_redirects=follow)
def login(u, p):
    t = tok(c.get('/login').get_data(as_text=True))
    return c.post('/login', data={'login': u, 'clave': p, 'csrf': t}, follow_redirects=True)
def stock(cod):
    return A.sqlite3.connect(os.environ['MS_DB']).execute('select stock_actual from producto where codigo=?', (cod,)).fetchone()[0]

print('Autenticación y permisos')
check('redirige a login sin sesión', c.get('/productos').status_code == 302)
check('rechaza clave incorrecta', 'incorrectos' in login('admin', 'mala').get_data(as_text=True))
check('POST sin token CSRF es rechazado', c.post('/login', data={'login': 'admin', 'clave': 'admin123'}).status_code == 400)
r = login('admin', 'admin123'); check('admin ingresa', 'Panel principal' in r.get_data(as_text=True))
for u in ['/productos', '/ventas', '/compras', '/reportes', '/movimientos', '/usuarios', '/clientes', '/proveedores', '/categorias', '/ventas/nueva', '/compras/nueva', '/perfil', '/productos/nuevo', '/reportes/inventario.xlsx']:
    check(f'admin abre {u}', c.get(u).status_code == 200)
check('respaldo descarga archivo', post('/respaldo', {}).data[:15] == b'SQLite format 3')

print('Inventario (datos demo, stock inicial por compra y ventas)')
check('EMP-001: 60 - 12 - 30 = 18', stock('EMP-001') == 18)
check('EMP-002: 50 - 35 = 15', stock('EMP-002') == 15)
db = A.sqlite3.connect(os.environ['MS_DB'])
check('movimientos registrados por triggers', db.execute("select count(*) from movimiento_inventario").fetchone()[0] == 9 + 6)

print('Ventas')
pid = {r[0]: r[1] for r in db.execute('select codigo,id_producto from producto')}
r = post('/ventas/nueva', {'id_producto': [pid['ARE-001']], 'cantidad': ['2'], 'metodo_pago': 'Efectivo', 'id_cliente': ''})
check('venta válida registrada', 'registrada' in r.get_data(as_text=True)); check('stock ARE-001 baja a 24', stock('ARE-001') == 24)
r = post('/ventas/nueva', {'id_producto': [pid['EMP-001']], 'cantidad': ['19'], 'metodo_pago': 'Efectivo'})
check('venta mayor al stock es rechazada', 'insuficientes' in r.get_data(as_text=True)); check('stock EMP-001 intacto (18)', stock('EMP-001') == 18)
r = post('/ventas/nueva', {'id_producto': [pid['EMP-001'], pid['EMP-001']], 'cantidad': ['10', '10'], 'metodo_pago': 'Efectivo'})
check('mismo producto repetido se suma y se rechaza (20 > 18)', 'insuficientes' in r.get_data(as_text=True))
r = post('/ventas/nueva', {'id_producto': [pid['EMP-001']], 'cantidad': ['-3'], 'metodo_pago': 'Efectivo'})
check('cantidad negativa rechazada', 'mayores que cero' in r.get_data(as_text=True))
r = post('/ventas/nueva', {'id_producto': [pid['INS-001']], 'cantidad': ['1'], 'metodo_pago': 'Efectivo'})
check('no se pueden vender insumos', 'no disponible' in r.get_data(as_text=True))
r = post('/ventas/nueva', {'id_producto': [pid['EMP-002']], 'cantidad': ['1'], 'metodo_pago': 'Bitcoin'})
check('método de pago inválido rechazado', 'método de pago' in r.get_data(as_text=True))
vt = db.execute('select total from venta order by id_venta desc limit 1').fetchone()[0]
check('total de venta = 2 x $3.00 (precio tomado de la BD)', vt == 6.0)

print('Compras')
r = post('/compras/nueva', {'id_proveedor': '1', 'id_producto': [pid['INS-002']], 'cantidad': ['10'], 'costo': ['5.5']})
check('compra registrada', 'registrada' in r.get_data(as_text=True)); check('stock INS-002: 9 + 10 = 19', stock('INS-002') == 19)
r = post('/compras/nueva', {'id_proveedor': '1', 'id_producto': [pid['INS-002']], 'cantidad': ['1'], 'costo': ['']})
check('compra sin costo rechazada', 'costo unitario' in r.get_data(as_text=True))

print('Productos, ajustes y alertas')
r = post('/productos/nuevo', {'codigo': 'bev-009', 'nombre': 'Refresco', 'id_categoria': '3', 'tipo': 'PRODUCTO', 'unidad_medida': 'botella', 'precio_venta': '1.2', 'costo': '0.7', 'stock_minimo': '5', 'stock_inicial': '8'})
check('producto nuevo con existencia inicial', stock('BEV-009') == 8)
r = post('/productos/nuevo', {'codigo': 'BEV-009', 'nombre': 'Dup', 'id_categoria': '3', 'tipo': 'PRODUCTO', 'unidad_medida': 'u'})
check('código duplicado rechazado', 'Ya existe' in r.get_data(as_text=True))
r = post(f'/productos/{pid["EMP-001"]}/ajuste', {'nuevo_stock': '25', 'motivo': 'Conteo físico'})
check('ajuste de inventario', stock('EMP-001') == 25)
check('ajuste queda en el historial', db.execute("select cantidad from movimiento_inventario where tipo='AJUSTE' and referencia like 'AJUSTE:%'").fetchone()[0] == 7)
h = c.get('/').get_data(as_text=True); check('panel muestra alertas de stock bajo', 'Existencias bajas' in h and 'EMP-002' in h)

print('Reportes')
h = c.get('/reportes').get_data(as_text=True); check('reportes muestran ventas y más vendidos', 'Ventas diarias' in h and 'Empanada de queso' in h)
x = c.get('/reportes/inventario.xlsx'); check('exporta Excel', x.data[:2] == b'PK')

print('Rol cajero')
c.post('/logout', data={'csrf': tok(c.get('/').get_data(as_text=True))})
r = login('cajero', 'cajero123'); check('cajero ingresa', 'Panel principal' in r.get_data(as_text=True))
for u in ['/compras', '/reportes', '/usuarios', '/productos/nuevo', '/movimientos', '/proveedores']:
    check(f'cajero NO accede a {u}', c.get(u).status_code == 302)
check('cajero puede abrir nueva venta', c.get('/ventas/nueva').status_code == 200)
check('cajero ve inventario', c.get('/productos').status_code == 200)
r = post('/ventas/nueva', {'id_producto': [pid['BEB-002']], 'cantidad': ['1'], 'metodo_pago': 'Pago móvil'}); check('cajero registra venta', 'registrada' in r.get_data(as_text=True))
vid_admin = db.execute('select id_venta from venta where id_usuario=1 limit 1').fetchone()[0]
check('cajero no ve ventas ajenas', c.get(f'/ventas/{vid_admin}').status_code == 403)
print(f'\n{ok} pruebas aprobadas')
