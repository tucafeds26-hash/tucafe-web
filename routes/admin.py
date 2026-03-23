from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_login import login_required, current_user
from functools import wraps
from config.database import db
from models.pedido import Pedido, ItemPedido
from models.producto import Producto
from models.usuario import Usuario
from datetime import datetime, timedelta, date
import os
from werkzeug.utils import secure_filename
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
import io

admin_bp = Blueprint('admin', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'img', 'productos')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def solo_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != 'admin':
            flash('Acceso denegado', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def calcular_corte(pedidos):
    total_ventas    = sum(float(p.total) for p in pedidos if p.pagado)
    total_efectivo  = sum(float(p.total) for p in pedidos if p.pagado and p.metodo_pago == 'efectivo')
    total_tarjeta   = sum(float(p.total) for p in pedidos if p.pagado and p.metodo_pago == 'tarjeta')
    num_pedidos     = len(pedidos)
    num_pagados     = sum(1 for p in pedidos if p.pagado)
    num_entregados  = sum(1 for p in pedidos if p.estado == 'entregado')
    ticket_promedio = total_ventas / num_pagados if num_pagados > 0 else 0

    horas = {}
    for p in pedidos:
        h = p.creado_en.hour
        horas[h] = horas.get(h, 0) + 1
    hora_pico = max(horas, key=horas.get) if horas else None

    SECCIONES = ['hamburguesas', 'pizza', 'tacos', 'sushi', 'postres']
    EMOJIS    = {'hamburguesas':'🍔','pizza':'🍕','tacos':'🌮','sushi':'🍱','postres':'🍰'}
    por_seccion = []
    for sec in SECCIONES:
        items_sec = [i for p in pedidos for i in p.items if i.producto and i.producto.categoria == sec]
        ingresos  = sum(i.subtotal() for i in items_sec if i.pedido.pagado)
        conteo    = {}
        for i in items_sec:
            nombre = i.producto.nombre if i.producto else 'N/A'
            conteo[nombre] = conteo.get(nombre, 0) + i.cantidad
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

@admin_bp.route('/')
@admin_bp.route('/dashboard')
@login_required
@solo_admin
def dashboard():
    pedidos = Pedido.query.filter_by(archivado=False).order_by(Pedido.creado_en.desc()).all()

    total_ingresos = sum(float(p.total) for p in pedidos if p.pagado)
    por_cobrar     = sum(float(p.total) for p in pedidos if not p.pagado)
    entregados     = sum(1 for p in pedidos if p.estado == 'entregado')
    en_preparacion = sum(1 for p in pedidos if p.estado in ('pendiente', 'en_preparacion'))

    SECCIONES = ['hamburguesas', 'pizza', 'tacos', 'sushi', 'postres']
    stats_por_seccion = []
    for sec in SECCIONES:
        items_sec   = [i for p in pedidos for i in p.items if i.producto and i.producto.categoria == sec]
        pedidos_sec = list({i.pedido_id for i in items_sec})
        ingresos    = sum(i.subtotal() for i in items_sec if i.pedido.pagado)
        stats_por_seccion.append({'nombre': sec, 'pedidos': len(pedidos_sec), 'ingresos': ingresos})

    return render_template('admin/dashboard.html',
        pedidos=pedidos[:20],
        total_ingresos=total_ingresos,
        por_cobrar=por_cobrar,
        total_pedidos=len(pedidos),
        pagados=sum(1 for p in pedidos if p.pagado),
        entregados=entregados,
        en_preparacion=en_preparacion,
        stats_por_seccion=stats_por_seccion,
    )

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
    pedidos = Pedido.query.filter(
        Pedido.creado_en >= inicio,
        Pedido.creado_en < fin
    ).order_by(Pedido.creado_en.asc()).all()

    stats         = calcular_corte(pedidos)
    ya_archivados = all(p.archivado for p in pedidos) if pedidos else False

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
        fecha_base = date.fromisoformat(fecha_str)
    except ValueError:
        fecha_base = date.today()

    inicio, fin, _ = get_periodo(tipo, fecha_base)
    pedidos = Pedido.query.filter(
        Pedido.creado_en >= inicio,
        Pedido.creado_en < fin,
        Pedido.archivado == False
    ).all()

    count = len(pedidos)
    for p in pedidos:
        p.archivado = True
    db.session.commit()

    flash(f'✅ Corte cerrado — {count} pedidos archivados correctamente', 'success')
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
    pedidos = Pedido.query.filter(
        Pedido.creado_en >= inicio,
        Pedido.creado_en < fin
    ).order_by(Pedido.creado_en.asc()).all()

    stats = calcular_corte(pedidos)
    buf   = io.BytesIO()
    W, H  = A4
    cv    = canvas.Canvas(buf, pagesize=A4)

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
        ('VENTAS TOTALES',  f'${stats["total_ventas"]:.2f}',   YELLOW, BLACK),
        ('PEDIDOS',         str(stats["num_pedidos"]),          TEAL,   WHITE),
        ('TICKET PROMEDIO', f'${stats["ticket_promedio"]:.2f}', GREEN,  WHITE),
        ('HORA PICO',       f'{stats["hora_pico"]:02d}:00' if stats["hora_pico"] is not None else '--:--', ORANGE, WHITE),
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
    cv.drawRightString(15*mm+hw-3*mm, y-5.5*mm, f'${stats["total_efectivo"]:.2f}')
    rr(15*mm+hw+2*mm, y-8*mm, hw, 8*mm, r=3, fill=colors.HexColor('#eff6ff'))
    cv.setFillColor(colors.HexColor('#1e40af'))
    cv.drawString(18*mm+hw+2*mm, y-5.5*mm, 'Tarjeta')
    cv.drawRightString(W-15*mm, y-5.5*mm, f'${stats["total_tarjeta"]:.2f}')
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

    for i, s in enumerate(stats['por_seccion']):
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
        cv.drawString(15*mm, y-4*mm, f'#{p.id}')
        cv.setFont('Helvetica', 7); cv.setFillColor(BLACK)
        cv.drawString(30*mm, y-4*mm, p.creado_en.strftime('%H:%M'))
        cv.drawString(48*mm, y-4*mm, (p.cliente.nombre if p.cliente else 'N/A')[:18])
        cv.drawString(100*mm, y-4*mm, p.hora_recoger.strftime('%H:%M') if p.hora_recoger else '—')
        cv.setFillColor(colors.HexColor('#166534') if p.pagado else colors.HexColor('#991b1b'))
        cv.drawString(130*mm, y-4*mm, f'${float(p.total):.2f}')
        cv.setFillColor(BLACK)
        cv.drawString(152*mm, y-4*mm, (p.metodo_pago or '—')[:8])
        estado_col = {
            'entregado':     colors.HexColor('#166534'),
            'en_preparacion':colors.HexColor('#9a3412'),
            'preparado':     colors.HexColor('#166534'),
        }.get(p.estado, DGRAY)
        cv.setFillColor(estado_col)
        cv.drawString(172*mm, y-4*mm, p.estado.replace('_',' ')[:10])
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

@admin_bp.route('/pedidos')
@login_required
@solo_admin
def pedidos():
    filtro = request.args.get('filtro', 'all')
    query  = Pedido.query.filter_by(archivado=False)
    if filtro == 'no_pagado':
        query = query.filter_by(pagado=False)
    elif filtro == 'abandonado':
        query = query.filter_by(estado='abandonado')
    elif filtro in ('hamburguesas','pizza','tacos','sushi','postres'):
        query = query.join(ItemPedido).join(Producto).filter(Producto.categoria == filtro)
    todos = query.order_by(Pedido.creado_en.desc()).all()
    return render_template('admin/pedidos.html', pedidos=todos, filtro=filtro)

@admin_bp.route('/pedidos/<int:pedido_id>/toggle-pago', methods=['POST'])
@login_required
@solo_admin
def toggle_pago(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    pedido.pagado = not pedido.pagado
    db.session.commit()
    return jsonify({'ok': True, 'pagado': pedido.pagado})

@admin_bp.route('/productos')
@login_required
@solo_admin
def productos():
    todos = Producto.query.order_by(Producto.categoria, Producto.nombre).all()
    return render_template('admin/productos.html', productos=todos)

@admin_bp.route('/productos/nuevo', methods=['GET', 'POST'])
@login_required
@solo_admin
def nuevo_producto():
    if request.method == 'POST':
        imagen_filename = None
        file = request.files.get('imagen')
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            imagen_filename = filename
        p = Producto(
            nombre      = request.form['nombre'],
            descripcion = request.form.get('descripcion', ''),
            precio      = float(request.form['precio']),
            categoria   = request.form['categoria'],
            emoji       = request.form.get('emoji', '🍽️'),
            disponible  = 'disponible' in request.form,
            imagen      = imagen_filename,
        )
        db.session.add(p)
        db.session.commit()
        flash('Producto creado correctamente', 'success')
        return redirect(url_for('admin.productos'))
    return render_template('admin/producto_form.html', producto=None)

@admin_bp.route('/productos/<int:prod_id>/editar', methods=['GET', 'POST'])
@login_required
@solo_admin
def editar_producto(prod_id):
    producto = Producto.query.get_or_404(prod_id)
    if request.method == 'POST':
        file = request.files.get('imagen')
        if file and file.filename and allowed_file(file.filename):
            if producto.imagen:
                old_path = os.path.join(UPLOAD_FOLDER, producto.imagen)
                if os.path.exists(old_path): os.remove(old_path)
            filename = secure_filename(file.filename)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            producto.imagen = filename
        producto.nombre      = request.form['nombre']
        producto.descripcion = request.form.get('descripcion', '')
        producto.precio      = float(request.form['precio'])
        producto.categoria   = request.form['categoria']
        producto.emoji       = request.form.get('emoji', '🍽️')
        producto.disponible  = 'disponible' in request.form
        db.session.commit()
        flash('Producto actualizado', 'success')
        return redirect(url_for('admin.productos'))
    return render_template('admin/producto_form.html', producto=producto)

@admin_bp.route('/productos/<int:prod_id>/eliminar', methods=['POST'])
@login_required
@solo_admin
def eliminar_producto(prod_id):
    producto = Producto.query.get_or_404(prod_id)
    if producto.imagen:
        img_path = os.path.join(UPLOAD_FOLDER, producto.imagen)
        if os.path.exists(img_path): os.remove(img_path)
    db.session.delete(producto)
    db.session.commit()
    flash('Producto eliminado', 'info')
    return redirect(url_for('admin.productos'))

@admin_bp.route('/usuarios')
@login_required
@solo_admin
def usuarios():
    todos = Usuario.query.order_by(Usuario.rol, Usuario.nombre).all()
    return render_template('admin/usuarios.html', usuarios=todos)