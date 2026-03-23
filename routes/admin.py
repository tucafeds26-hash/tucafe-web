from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response, session
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, timedelta, date
import os, io, requests
from werkzeug.utils import secure_filename
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm

admin_bp = Blueprint('admin', __name__)

API_URL = 'https://tucafe-api-production.up.railway.app/api/v1'
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'img', 'productos')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_token():
    return session.get('jwt_token', '')

def api_headers():
    return {'Authorization': f'Bearer {get_token()}'}

def solo_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != 'admin':
            flash('Acceso denegado', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def get_periodo(tipo, fecha_base):
    if tipo == 'semanal':
        inicio = datetime.combine(fecha_base - timedelta(days=fecha_base.weekday()), datetime.min.time())
        fin    = inicio + timedelta(days=7)
        titulo = f'Corte Semanal — Semana del {inicio.strftime("%d/%m/%Y")}'
    else:
        inicio = datetime.combine(fecha_base, datetime.min.time())
        fin    = inicio + timedelta(days=1)
        titulo = f'Corte Diario — {fecha_base.strftime("%d/%m/%Y")}'
    return inicio, fin, titulo

def calcular_corte_desde_api(pedidos_raw):
    """Calcula estadisticas desde los dicts que devuelve la API."""
    total_ventas    = sum(float(p['total']) for p in pedidos_raw if p['pagado'])
    total_efectivo  = sum(float(p['total']) for p in pedidos_raw if p['pagado'] and p.get('metodo_pago') == 'efectivo')
    total_tarjeta   = sum(float(p['total']) for p in pedidos_raw if p['pagado'] and p.get('metodo_pago') == 'tarjeta')
    num_pedidos     = len(pedidos_raw)
    num_pagados     = sum(1 for p in pedidos_raw if p['pagado'])
    num_entregados  = sum(1 for p in pedidos_raw if p['estado'] == 'entregado')
    ticket_promedio = total_ventas / num_pagados if num_pagados > 0 else 0

    horas = {}
    for p in pedidos_raw:
        try:
            h = datetime.fromisoformat(p['creado_en']).hour
            horas[h] = horas.get(h, 0) + 1
        except:
            pass
    hora_pico = max(horas, key=horas.get) if horas else None

    SECCIONES = ['hamburguesas', 'pizza', 'tacos', 'sushi', 'postres']
    EMOJIS    = {'hamburguesas':'🍔','pizza':'🍕','tacos':'🌮','sushi':'🍱','postres':'🍰'}
    por_seccion = []
    for sec in SECCIONES:
        items_sec = [i for p in pedidos_raw for i in p.get('items', [])
                     if i.get('producto') and i['producto'].get('categoria') == sec]
        ingresos  = sum(float(i['subtotal']) for i in items_sec
                        if next((p for p in pedidos_raw if p['id'] == i.get('pedido_id', -1) and p['pagado']), None))
        conteo    = {}
        for i in items_sec:
            nombre = i['producto']['nombre'] if i.get('producto') else 'N/A'
            conteo[nombre] = conteo.get(nombre, 0) + i['cantidad']
        top = max(conteo, key=conteo.get) if conteo else '—'
        por_seccion.append({
            'nombre':   sec,
            'emoji':    EMOJIS[sec],
            'ingresos': ingresos,
            'cantidad': len(items_sec),
            'top':      top,
        })

    return {
        'total_ventas':    total_ventas,
        'total_efectivo':  total_efectivo,
        'total_tarjeta':   total_tarjeta,
        'num_pedidos':     num_pedidos,
        'num_pagados':     num_pagados,
        'num_entregados':  num_entregados,
        'ticket_promedio': ticket_promedio,
        'hora_pico':       hora_pico,
        'por_seccion':     por_seccion,
    }

# ── DASHBOARD ─────────────────────────────────────────────────
@admin_bp.route('/')
@admin_bp.route('/dashboard')
@login_required
@solo_admin
def dashboard():
    try:
        r    = requests.get(f'{API_URL}/admin/dashboard', headers=api_headers())
        data = r.json()
        pedidos           = data.get('pedidos', [])
        total_ingresos    = data.get('total_ingresos', 0)
        por_cobrar        = data.get('por_cobrar', 0)
        total_pedidos     = data.get('total_pedidos', 0)
        pagados           = data.get('pagados', 0)
        entregados        = data.get('entregados', 0)
        en_preparacion    = data.get('en_preparacion', 0)
        stats_por_seccion = data.get('stats_por_seccion', [])
    except:
        pedidos = []; total_ingresos = 0; por_cobrar = 0
        total_pedidos = 0; pagados = 0; entregados = 0
        en_preparacion = 0; stats_por_seccion = []

    return render_template('admin/dashboard.html',
        pedidos=pedidos,
        total_ingresos=total_ingresos,
        por_cobrar=por_cobrar,
        total_pedidos=total_pedidos,
        pagados=pagados,
        entregados=entregados,
        en_preparacion=en_preparacion,
        stats_por_seccion=stats_por_seccion,
    )

# ── CORTE ─────────────────────────────────────────────────────
@admin_bp.route('/corte')
@login_required
@solo_admin
def corte():
    tipo      = request.args.get('tipo', 'diario')
    fecha_str = request.args.get('fecha', date.today().isoformat())
    try:
        fecha_base = date.fromisoformat(fecha_str)
    except ValueError:
        fecha_base = date.today()

    inicio, fin, titulo = get_periodo(tipo, fecha_base)
    try:
        r    = requests.get(f'{API_URL}/admin/corte', headers=api_headers(), params={
            'tipo': tipo, 'fecha': fecha_str
        })
        data          = r.json()
        pedidos       = data.get('pedidos', [])
        stats         = data.get('stats', {})
        ya_archivados = data.get('ya_archivados', False)
    except:
        pedidos = []; stats = {}; ya_archivados = False

    return render_template('admin/corte.html',
        titulo=titulo, tipo=tipo,
        fecha=fecha_base.isoformat(),
        pedidos=pedidos, stats=stats,
        inicio=inicio, fin=fin,
        now=datetime.now(),
        ya_archivados=ya_archivados,
    )

@admin_bp.route('/corte/cerrar', methods=['POST'])
@login_required
@solo_admin
def cerrar_corte():
    tipo      = request.form.get('tipo', 'diario')
    fecha_str = request.form.get('fecha', date.today().isoformat())
    try:
        r    = requests.post(f'{API_URL}/admin/corte/cerrar', headers=api_headers(),
                             json={'tipo': tipo, 'fecha': fecha_str})
        data = r.json()
        count = data.get('count', 0)
        flash(f'✅ Corte cerrado — {count} pedidos archivados correctamente', 'success')
    except:
        flash('Error al cerrar el corte', 'error')
    return redirect(url_for('admin.corte', tipo=tipo, fecha=fecha_str))

@admin_bp.route('/corte/pdf')
@login_required
@solo_admin
def corte_pdf():
    tipo      = request.args.get('tipo', 'diario')
    fecha_str = request.args.get('fecha', date.today().isoformat())
    try:
        fecha_base = date.fromisoformat(fecha_str)
    except ValueError:
        fecha_base = date.today()

    inicio, fin, titulo = get_periodo(tipo, fecha_base)
    try:
        r       = requests.get(f'{API_URL}/admin/corte', headers=api_headers(),
                               params={'tipo': tipo, 'fecha': fecha_str})
        data    = r.json()
        pedidos = data.get('pedidos', [])
        stats   = data.get('stats', {})
    except:
        pedidos = []; stats = {}

    buf  = io.BytesIO()
    W, H = A4
    cv   = canvas.Canvas(buf, pagesize=A4)

    YELLOW = colors.HexColor('#FFD600')
    BLACK  = colors.HexColor('#111111')
    DARK   = colors.HexColor('#1a1a1a')
    TEAL   = colors.HexColor('#14b8a6')
    GREEN  = colors.HexColor('#22c55e')
    ORANGE = colors.HexColor('#f97316')
    WHITE  = colors.white
    LGRAY  = colors.HexColor('#f5f5f5')
    DGRAY  = colors.HexColor('#6b7280')

    def rr(x, y, w, h, r=4, fill=None, stroke=None, sw=1):
        p = cv.beginPath()
        p.moveTo(x+r, y); p.lineTo(x+w-r, y)
        p.arcTo(x+w-r, y, x+w, y+r, startAng=270, extent=90)
        p.lineTo(x+w, y+h-r)
        p.arcTo(x+w-r, y+h-r, x+w, y+h, startAng=0, extent=90)
        p.lineTo(x+r, y+h)
        p.arcTo(x, y+h-r, x+r, y+h, startAng=90, extent=90)
        p.lineTo(x, y+r)
        p.arcTo(x, y, x+r, y+r, startAng=180, extent=90)
        p.close()
        if fill:   cv.setFillColor(fill)
        if stroke: cv.setStrokeColor(stroke); cv.setLineWidth(sw)
        if fill and stroke: cv.drawPath(p, fill=1, stroke=1)
        elif fill:          cv.drawPath(p, fill=1, stroke=0)
        elif stroke:        cv.drawPath(p, fill=0, stroke=1)

    rr(0, H-45*mm, W, 45*mm, r=0, fill=BLACK)
    cv.setFillColor(WHITE); cv.setFont('Helvetica-Bold', 24)
    cv.drawString(15*mm, H-16*mm, 'TU ')
    tw = cv.stringWidth('TU ', 'Helvetica-Bold', 24)
    cv.setFillColor(YELLOW)
    cv.drawString(15*mm+tw, H-16*mm, 'CAFE')
    cv.setFillColor(WHITE); cv.setFont('Helvetica-Bold', 12)
    cv.drawString(15*mm, H-25*mm, titulo)
    cv.setFont('Helvetica', 9); cv.setFillColor(colors.HexColor('#94a3b8'))
    cv.drawString(15*mm, H-33*mm, f'Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")}  |  Admin: {current_user.nombre}')
    cv.drawRightString(W-15*mm, H-25*mm, f'{inicio.strftime("%d/%m/%Y")} — {fin.strftime("%d/%m/%Y")}')

    y = H - 52*mm
    cw = (W - 32*mm) / 4
    cards_data = [
        ('VENTAS TOTALES',  f'${stats.get("total_ventas", 0):.2f}',   YELLOW, BLACK),
        ('PEDIDOS',         str(stats.get("num_pedidos", 0)),          TEAL,   WHITE),
        ('TICKET PROMEDIO', f'${stats.get("ticket_promedio", 0):.2f}', GREEN,  WHITE),
        ('HORA PICO',       f'{stats.get("hora_pico", 0):02d}:00' if stats.get("hora_pico") is not None else '--:--', ORANGE, WHITE),
    ]
    for i, (lbl, val, bg, fg) in enumerate(cards_data):
        cx = 15*mm + i*(cw+2*mm)
        rr(cx, y-20*mm, cw, 20*mm, r=5, fill=bg)
        cv.setFont('Helvetica-Bold', 7)
        cv.setFillColor(BLACK if bg == YELLOW else WHITE)
        cv.drawCentredString(cx+cw/2, y-7*mm, lbl)
        cv.setFont('Helvetica-Bold', 14)
        cv.drawCentredString(cx+cw/2, y-16*mm, val)
    y -= 26*mm

    cv.setFont('Helvetica-Bold', 9); cv.setFillColor(BLACK)
    cv.drawString(15*mm, y, 'METODOS DE PAGO')
    cv.setStrokeColor(colors.HexColor('#e5e7eb')); cv.setLineWidth(0.5)
    cv.line(15*mm, y-1.5*mm, W-15*mm, y-1.5*mm)
    y -= 7*mm

    hw = (W-32*mm)/2
    rr(15*mm, y-8*mm, hw, 8*mm, r=3, fill=colors.HexColor('#f0fdf4'))
    cv.setFont('Helvetica-Bold', 9); cv.setFillColor(colors.HexColor('#166534'))
    cv.drawString(18*mm, y-5.5*mm, 'Efectivo')
    cv.drawRightString(15*mm+hw-3*mm, y-5.5*mm, f'${stats.get("total_efectivo", 0):.2f}')
    rr(15*mm+hw+2*mm, y-8*mm, hw, 8*mm, r=3, fill=colors.HexColor('#eff6ff'))
    cv.setFillColor(colors.HexColor('#1e40af'))
    cv.drawString(18*mm+hw+2*mm, y-5.5*mm, 'Tarjeta')
    cv.drawRightString(W-15*mm, y-5.5*mm, f'${stats.get("total_tarjeta", 0):.2f}')
    y -= 13*mm

    cv.setFont('Helvetica-Bold', 9); cv.setFillColor(BLACK)
    cv.drawString(15*mm, y, 'VENTAS POR SECCION')
    cv.line(15*mm, y-1.5*mm, W-15*mm, y-1.5*mm)
    y -= 7*mm

    rr(15*mm, y-6*mm, W-30*mm, 6*mm, r=3, fill=BLACK)
    cv.setFont('Helvetica-Bold', 7.5); cv.setFillColor(YELLOW)
    for lbl, xp in [('Seccion',15),('Ingresos',100),('Cantidad',145),('Producto estrella',165)]:
        cv.drawString(xp*mm, y-4.5*mm, lbl)
    y -= 6*mm

    for i, s in enumerate(stats.get('por_seccion', [])):
        bg = LGRAY if i%2==0 else WHITE
        rr(15*mm, y-6*mm, W-30*mm, 6*mm, r=0, fill=bg, stroke=colors.HexColor('#e5e7eb'), sw=0.3)
        cv.setFont('Helvetica-Bold', 8); cv.setFillColor(BLACK)
        cv.drawString(15*mm+2*mm, y-4.5*mm, s['nombre'].title())
        cv.setFont('Helvetica', 8)
        cv.setFillColor(colors.HexColor('#166534') if s['ingresos']>0 else DGRAY)
        cv.drawString(100*mm, y-4.5*mm, f'${s["ingresos"]:.2f}')
        cv.setFillColor(BLACK)
        cv.drawString(145*mm, y-4.5*mm, str(s['cantidad']))
        cv.setFillColor(DGRAY)
        cv.drawString(165*mm, y-4.5*mm, s['top'][:22])
        y -= 6*mm
    y -= 5*mm

    cv.setFont('Helvetica-Bold', 9); cv.setFillColor(BLACK)
    cv.drawString(15*mm, y, f'RESUMEN DE PEDIDOS ({len(pedidos)} en total)')
    cv.line(15*mm, y-1.5*mm, W-15*mm, y-1.5*mm)
    y -= 7*mm

    rr(15*mm, y-6*mm, W-30*mm, 6*mm, r=3, fill=DARK)
    cv.setFont('Helvetica-Bold', 7.5); cv.setFillColor(YELLOW)
    for lbl, xp in [('#ID',15),('Hora',30),('Cliente',48),('Recoger',100),('Total',130),('Metodo',152),('Estado',172)]:
        cv.drawString(xp*mm, y-4.5*mm, lbl)
    y -= 6*mm

    for i, p in enumerate(pedidos):
        if y < 25*mm:
            cv.showPage()
            y = H - 20*mm
        bg = LGRAY if i%2==0 else WHITE
        rr(15*mm, y-5.5*mm, W-30*mm, 5.5*mm, r=0, fill=bg, stroke=colors.HexColor('#e5e7eb'), sw=0.3)
        cv.setFont('Helvetica-Bold', 7); cv.setFillColor(ORANGE)
        cv.drawString(15*mm, y-4*mm, f'#{p["id"]}')
        cv.setFont('Helvetica', 7); cv.setFillColor(BLACK)
        try:
            hora = datetime.fromisoformat(p['creado_en']).strftime('%H:%M')
        except:
            hora = '--:--'
        cv.drawString(30*mm, y-4*mm, hora)
        cv.drawString(48*mm, y-4*mm, str(p.get('cliente_nombre', 'N/A'))[:18])
        cv.drawString(100*mm, y-4*mm, p.get('hora_recoger') or '—')
        cv.setFillColor(colors.HexColor('#166534') if p['pagado'] else colors.HexColor('#991b1b'))
        cv.drawString(130*mm, y-4*mm, f'${float(p["total"]):.2f}')
        cv.setFillColor(BLACK)
        cv.drawString(152*mm, y-4*mm, (p.get('metodo_pago') or '—')[:8])
        estado_col = {
            'entregado':      colors.HexColor('#166534'),
            'en_preparacion': colors.HexColor('#9a3412'),
            'preparado':      colors.HexColor('#166534'),
        }.get(p.get('estado', ''), DGRAY)
        cv.setFillColor(estado_col)
        cv.drawString(172*mm, y-4*mm, str(p.get('estado', '')).replace('_',' ')[:10])
        y -= 5.5*mm

    cv.setFillColor(BLACK)
    cv.rect(0, 0, W, 10*mm, fill=1, stroke=0)
    cv.setFillColor(WHITE); cv.setFont('Helvetica', 7.5)
    cv.drawCentredString(W/2, 4*mm, f'TU CAFE — {titulo} — {datetime.now().strftime("%d/%m/%Y %H:%M")} — {current_user.nombre}')
    cv.save()
    buf.seek(0)
    response = make_response(buf.read())
    response.headers['Content-Type']        = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=corte_{tipo}_{fecha_base.isoformat()}.pdf'
    return response

# ── PEDIDOS ───────────────────────────────────────────────────
@admin_bp.route('/pedidos')
@login_required
@solo_admin
def pedidos():
    filtro = request.args.get('filtro', 'all')
    try:
        r    = requests.get(f'{API_URL}/admin/pedidos', headers=api_headers(), params={'filtro': filtro})
        data = r.json()
        todos = data.get('pedidos', [])
    except:
        todos = []
    return render_template('admin/pedidos.html', pedidos=todos, filtro=filtro)

@admin_bp.route('/pedidos/<int:pedido_id>/toggle-pago', methods=['POST'])
@login_required
@solo_admin
def toggle_pago(pedido_id):
    try:
        r    = requests.post(f'{API_URL}/admin/pedidos/{pedido_id}/toggle-pago', headers=api_headers())
        data = r.json()
        return jsonify(data), r.status_code
    except:
        return jsonify({'error': 'Error al conectar'}), 500

# ── PRODUCTOS ─────────────────────────────────────────────────
@admin_bp.route('/productos')
@login_required
@solo_admin
def productos():
    try:
        r    = requests.get(f'{API_URL}/admin/productos', headers=api_headers())
        data = r.json()
        todos = data.get('productos', [])
    except:
        todos = []
    return render_template('admin/productos.html', productos=todos)

@admin_bp.route('/productos/nuevo', methods=['GET', 'POST'])
@login_required
@solo_admin
def nuevo_producto():
    if request.method == 'POST':
        try:
            # Subir imagen local primero
            imagen_filename = None
            file = request.files.get('imagen')
            if file and file.filename and allowed_file(file.filename):
                from werkzeug.utils import secure_filename
                filename = secure_filename(file.filename)
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                file.save(os.path.join(UPLOAD_FOLDER, filename))
                imagen_filename = filename

            r = requests.post(f'{API_URL}/admin/productos', headers=api_headers(), json={
                'nombre':      request.form['nombre'],
                'descripcion': request.form.get('descripcion', ''),
                'precio':      float(request.form['precio']),
                'categoria':   request.form['categoria'],
                'emoji':       request.form.get('emoji', '🍽️'),
                'disponible':  'disponible' in request.form,
                'imagen':      imagen_filename,
            })
            if r.status_code == 201:
                flash('Producto creado correctamente', 'success')
                return redirect(url_for('admin.productos'))
            else:
                flash(r.json().get('error', 'Error al crear'), 'error')
        except Exception as e:
            flash('Error al conectar con el servidor', 'error')
    return render_template('admin/producto_form.html', producto=None)

@admin_bp.route('/productos/<int:prod_id>/editar', methods=['GET', 'POST'])
@login_required
@solo_admin
def editar_producto(prod_id):
    try:
        r        = requests.get(f'{API_URL}/productos/{prod_id}')
        producto = r.json().get('producto', {})
    except:
        producto = {}

    if request.method == 'POST':
        try:
            imagen_filename = producto.get('imagen')
            file = request.files.get('imagen')
            if file and file.filename and allowed_file(file.filename):
                from werkzeug.utils import secure_filename
                filename = secure_filename(file.filename)
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                file.save(os.path.join(UPLOAD_FOLDER, filename))
                imagen_filename = filename

            r = requests.put(f'{API_URL}/admin/productos/{prod_id}', headers=api_headers(), json={
                'nombre':      request.form['nombre'],
                'descripcion': request.form.get('descripcion', ''),
                'precio':      float(request.form['precio']),
                'categoria':   request.form['categoria'],
                'emoji':       request.form.get('emoji', '🍽️'),
                'disponible':  'disponible' in request.form,
                'imagen':      imagen_filename,
            })
            if r.status_code == 200:
                flash('Producto actualizado', 'success')
                return redirect(url_for('admin.productos'))
            else:
                flash(r.json().get('error', 'Error al actualizar'), 'error')
        except:
            flash('Error al conectar con el servidor', 'error')
    return render_template('admin/producto_form.html', producto=producto)

@admin_bp.route('/productos/<int:prod_id>/eliminar', methods=['POST'])
@login_required
@solo_admin
def eliminar_producto(prod_id):
    try:
        r = requests.delete(f'{API_URL}/admin/productos/{prod_id}', headers=api_headers())
        if r.status_code == 200:
            flash('Producto eliminado', 'info')
        else:
            flash('Error al eliminar', 'error')
    except:
        flash('Error al conectar con el servidor', 'error')
    return redirect(url_for('admin.productos'))

# ── USUARIOS ──────────────────────────────────────────────────
@admin_bp.route('/usuarios')
@login_required
@solo_admin
def usuarios():
    try:
        r    = requests.get(f'{API_URL}/admin/usuarios', headers=api_headers())
        data = r.json()
        todos = data.get('usuarios', [])
    except:
        todos = []
    return render_template('admin/usuarios.html', usuarios=todos)