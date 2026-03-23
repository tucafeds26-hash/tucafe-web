from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from datetime import datetime, timedelta, time
import requests, qrcode, io, base64, stripe, os

pedidos_bp = Blueprint('pedidos', __name__)
API_URL = 'https://tucafe-api-production.up.railway.app/api/v1'
STRIPE_SK = os.environ.get('STRIPE_SK', '')

def get_token():
    return session.get('jwt_token', '')

def api_headers():
    return {'Authorization': f'Bearer {get_token()}'}

def generar_qr_base64(pedido_id):
    qr = qrcode.QRCode(version=1, box_size=8, border=4)
    qr.add_data(str(pedido_id))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode('utf-8')

def generar_horas_recoger():
    import pytz
    from datetime import datetime, timedelta, time as dtime

    tz_mexico   = pytz.timezone('America/Mexico_City')
    ahora       = datetime.now(tz_mexico).replace(tzinfo=None)
    minimo      = ahora + timedelta(minutes=20)
    hora_actual = ahora.hour

    if hora_actual < 15:
        turno_inicio = datetime.combine(ahora.date(), dtime(8, 0))
        turno_fin    = datetime.combine(ahora.date(), dtime(14, 0))
        turno_nombre = 'Matutino'
    else:
        turno_inicio = datetime.combine(ahora.date(), dtime(15, 0))
        turno_fin    = datetime.combine(ahora.date(), dtime(20, 0))
        turno_nombre = 'Vespertino'

    slots = []
    t = turno_inicio
    while t <= turno_fin:
        if t >= minimo:
            slots.append(t.strftime('%H:%M'))
        t += timedelta(minutes=15)

    return slots, turno_nombre

# ── CARRITO (se queda en sesion, no necesita API) ─────────────
@pedidos_bp.route('/carrito')
@login_required
def carrito():
    carrito_ses = session.get('carrito', {})
    items, total = [], 0
    for prod_id, cantidad in carrito_ses.items():
        try:
            r        = requests.get(f'{API_URL}/productos/{prod_id}')
            producto = r.json().get('producto')
            if producto:
                subtotal = float(producto['precio']) * cantidad
                total   += subtotal
                items.append({'producto': producto, 'cantidad': cantidad, 'subtotal': subtotal})
        except:
            pass
    return render_template('carrito.html', items=items, total=total)

@pedidos_bp.route('/carrito/agregar', methods=['POST'])
@login_required
def agregar_al_carrito():
    producto_id = request.form.get('producto_id')
    cantidad    = int(request.form.get('cantidad', 1))
    if not producto_id:
        return jsonify({'error': 'Producto no valido'}), 400
    carrito = session.get('carrito', {})
    carrito[str(producto_id)] = carrito.get(str(producto_id), 0) + cantidad
    session['carrito']  = carrito
    session.modified    = True
    return jsonify({'ok': True, 'total_items': sum(carrito.values())})

@pedidos_bp.route('/carrito/quitar', methods=['POST'])
@login_required
def quitar_del_carrito():
    producto_id = request.form.get('producto_id')
    carrito     = session.get('carrito', {})
    carrito.pop(str(producto_id), None)
    session['carrito'] = carrito
    session.modified   = True
    return jsonify({'ok': True})

@pedidos_bp.route('/carrito/actualizar', methods=['POST'])
@login_required
def actualizar_carrito():
    producto_id = request.form.get('producto_id')
    cantidad    = int(request.form.get('cantidad', 1))
    carrito     = session.get('carrito', {})
    if cantidad <= 0:
        carrito.pop(str(producto_id), None)
    else:
        carrito[str(producto_id)] = cantidad
    session['carrito'] = carrito
    session.modified   = True
    return jsonify({'ok': True})

# ── CHECKOUT ──────────────────────────────────────────────────
@pedidos_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    carrito_ses = session.get('carrito', {})
    if not carrito_ses:
        flash('Tu carrito esta vacio', 'warning')
        return redirect(url_for('menu.tienda'))

    if request.method == 'POST':
        notas       = request.form.get('notas', '')
        metodo_pago = request.form.get('metodo_pago', 'efectivo')
        hora_str    = request.form.get('hora_recoger', '')

        items_api = []
        for prod_id, cantidad in carrito_ses.items():
            items_api.append({'producto_id': int(prod_id), 'cantidad': cantidad})

        try:
            print(f"[WEB] Enviando pedido a API: items={items_api}, hora={hora_str}")
            r = requests.post(f'{API_URL}/pedidos/crear',
                headers=api_headers(),
                json={
                    'items':        items_api,
                    'notas':        notas,
                    'metodo_pago':  metodo_pago,
                    'hora_recoger': hora_str or None,
                })
            print(f"[WEB] Respuesta API: status={r.status_code}, body={r.text}")
            data = r.json()
            if r.status_code == 201 and data.get('ok'):
                print(f"[WEB] Pedido creado exitosamente")
                session.pop('carrito', None)
                pedido_id = data['pedido']['id']
                if metodo_pago == 'tarjeta':
                    return redirect(url_for('pedidos.pago_stripe', pedido_id=pedido_id))
                return redirect(url_for('pedidos.ver_qr', pedido_id=pedido_id))
            else:
                error_msg = data.get('error', 'Error al crear pedido')
                print(f"[WEB] Error: {error_msg}")
                flash(error_msg, 'error')
        except Exception as e:
            print(f"[WEB] Excepción: {e}")
            flash('Error al conectar con el servidor', 'error')

    items, total = [], 0
    for prod_id, cantidad in carrito_ses.items():
        try:
            r        = requests.get(f'{API_URL}/productos/{prod_id}')
            producto = r.json().get('producto')
            if producto:
                subtotal = float(producto['precio']) * cantidad
                total   += subtotal
                items.append({'producto': producto, 'cantidad': cantidad, 'subtotal': subtotal})
        except:
            pass

    horas, turno_nombre = generar_horas_recoger()
    return render_template('checkout.html', items=items, total=total,
                           horas=horas, turno_nombre=turno_nombre)

# ── STRIPE ────────────────────────────────────────────────────
@pedidos_bp.route('/pago/<int:pedido_id>')
@login_required
def pago_stripe(pedido_id):
    try:
        r      = requests.get(f'{API_URL}/pedidos/{pedido_id}', headers=api_headers())
        pedido = r.json().get('pedido')
        if not pedido:
            flash('Pedido no encontrado', 'error')
            return redirect(url_for('pedidos.mis_pedidos'))
    except:
        flash('Error al conectar con el servidor', 'error')
        return redirect(url_for('pedidos.mis_pedidos'))

    stripe.api_key = STRIPE_SK
    line_items = []
    for item in pedido.get('items', []):
        line_items.append({
            'price_data': {
                'currency': 'mxn',
                'product_data': {
                    'name':        item['producto']['nombre']      if item.get('producto') else 'Producto',
                    'description': item['producto']['descripcion'] if item.get('producto') else '',
                },
                'unit_amount': int(float(item['precio_unit']) * 100),
            },
            'quantity': item['cantidad'],
        })

    checkout_session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=line_items,
        mode='payment',
        success_url=url_for('pedidos.pago_exitoso',   pedido_id=pedido_id, _external=True),
        cancel_url =url_for('pedidos.pago_cancelado', pedido_id=pedido_id, _external=True),
        metadata={'pedido_id': pedido_id}
    )
    return redirect(checkout_session.url, code=303)

@pedidos_bp.route('/pago/exitoso/<int:pedido_id>')
@login_required
def pago_exitoso(pedido_id):
    try:
        requests.post(f'{API_URL}/pedidos/{pedido_id}/pagar', headers=api_headers())
    except:
        pass
    flash('Pago exitoso con tarjeta', 'success')
    return redirect(url_for('pedidos.ver_qr', pedido_id=pedido_id))

@pedidos_bp.route('/pago/cancelado/<int:pedido_id>')
@login_required
def pago_cancelado(pedido_id):
    flash('Pago cancelado. Tu pedido sigue guardado.', 'warning')
    return redirect(url_for('pedidos.ver_qr', pedido_id=pedido_id))

# ── QR ────────────────────────────────────────────────────────
@pedidos_bp.route('/qr/<int:pedido_id>')
@login_required
def ver_qr(pedido_id):
    try:
        r      = requests.get(f'{API_URL}/pedidos/{pedido_id}', headers=api_headers())
        data   = r.json()
        pedido = data.get('pedido')
        qr_b64 = data.get('qr') or generar_qr_base64(pedido_id)
    except:
        pedido = None
        qr_b64 = generar_qr_base64(pedido_id)
    return render_template('qr_pedido.html', pedido=pedido, qr_b64=qr_b64)

@pedidos_bp.route('/recibo/<int:pedido_id>')
@login_required
def recibo(pedido_id):
    try:
        r      = requests.get(f'{API_URL}/pedidos/{pedido_id}', headers=api_headers())
        pedido = r.json().get('pedido')
    except:
        pedido = None
    qr_b64 = generar_qr_base64(pedido_id)
    return render_template('recibo.html', pedido=pedido, qr_b64=qr_b64)

# ── ESCANEAR ──────────────────────────────────────────────────
@pedidos_bp.route('/escanear', methods=['GET', 'POST'])
@login_required
def escanear():
    if current_user.rol not in ('admin', 'chef'):
        flash('Acceso denegado', 'error')
        return redirect(url_for('menu.index'))
    pedido = None
    if request.method == 'POST':
        pedido_id = request.form.get('pedido_id', '').strip()
        if pedido_id.isdigit():
            try:
                r      = requests.get(f'{API_URL}/pedidos/{pedido_id}', headers=api_headers())
                pedido = r.json().get('pedido')
                if not pedido:
                    flash('No existe pedido con ese ID', 'error')
            except:
                flash('Error al buscar pedido', 'error')
        else:
            flash('QR invalido', 'error')
    return render_template('escanear.html', pedido=pedido)

@pedidos_bp.route('/escanear/<int:pedido_id>/pagar', methods=['POST'])
@login_required
def marcar_pagado(pedido_id):
    if current_user.rol != 'admin':
        return jsonify({'error': 'Sin permiso'}), 403
    try:
        r    = requests.post(f'{API_URL}/pedidos/{pedido_id}/pagar', headers=api_headers())
        data = r.json()
        return jsonify(data), r.status_code
    except:
        return jsonify({'error': 'Error al conectar'}), 500

@pedidos_bp.route('/escanear/<int:pedido_id>/entregar', methods=['POST'])
@login_required
def marcar_entregado_qr(pedido_id):
    if current_user.rol not in ('admin', 'chef'):
        return jsonify({'error': 'Sin permiso'}), 403
    try:
        r    = requests.post(f'{API_URL}/pedidos/{pedido_id}/entregar', headers=api_headers())
        data = r.json()
        return jsonify(data), r.status_code
    except:
        return jsonify({'error': 'Error al conectar'}), 500

@pedidos_bp.route('/escanear/<int:pedido_id>/entregar_seccion', methods=['POST'])
@login_required
def entregar_seccion(pedido_id):
    if current_user.rol not in ('admin', 'chef'):
        return jsonify({'error': 'Sin permiso'}), 403
    try:
        r    = requests.post(f'{API_URL}/pedidos/{pedido_id}/entregar_seccion', headers=api_headers())
        data = r.json()
        return jsonify(data), r.status_code
    except:
        return jsonify({'error': 'Error al conectar'}), 500

# ── MIS PEDIDOS ───────────────────────────────────────────────
@pedidos_bp.route('/mis-pedidos')
@login_required
def mis_pedidos():
    try:
        r    = requests.get(f'{API_URL}/pedidos/', headers=api_headers())
        data = r.json()
        activos = data.get('activos', [])
        listos  = [p for p in activos if p.get('notificacion')]
    except:
        activos = []
        listos  = []
    ahora = datetime.now().time()
    return render_template('mis_pedidos.html', activos=activos,
                           historial=[], listos=listos, ahora=ahora)

# ── NOTIFICACIONES ────────────────────────────────────────────
@pedidos_bp.route('/notificacion/vista/<int:pedido_id>', methods=['POST'])
@login_required
def marcar_notificacion_vista(pedido_id):
    try:
        r    = requests.post(f'{API_URL}/pedidos/{pedido_id}/notificacion/vista', headers=api_headers())
        data = r.json()
        return jsonify(data), r.status_code
    except:
        return jsonify({'ok': True}), 200

@pedidos_bp.route('/notificaciones/check')
@login_required
def check_notificaciones():
    try:
        r    = requests.get(f'{API_URL}/pedidos/notificaciones', headers=api_headers())
        data = r.json()
        return jsonify({'tiene': data.get('tiene', False)})
    except:
        return jsonify({'tiene': False})

@pedidos_bp.route('/<int:pedido_id>/abandonado', methods=['POST'])
@login_required
def marcar_abandonado(pedido_id):
    try:
        r    = requests.post(f'{API_URL}/pedidos/{pedido_id}/abandonado', headers=api_headers())
        data = r.json()
        return jsonify(data), r.status_code
    except:
        return jsonify({'ok': True}), 200