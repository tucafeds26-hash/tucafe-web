from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
import requests

chef_bp = Blueprint('chef', __name__)

API_URL = 'http://localhost:5001/api/v1'

def get_token():
    from flask import session
    return session.get('jwt_token', '')

def api_headers():
    return {'Authorization': f'Bearer {get_token()}'}

def solo_chef(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol not in ('chef', 'admin'):
            flash('Acceso denegado', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

@chef_bp.route('/')
@chef_bp.route('/comandas')
@login_required
@solo_chef
def comandas():
    try:
        r    = requests.get(f'{API_URL}/chef/comandas', headers=api_headers())
        data = r.json()
        pedidos_raw = data.get('comandas', [])
    except:
        pedidos_raw = []

    # Convertir dicts a objetos simples para el template
    class PedidoProxy:
        def __init__(self, d):
            self.__dict__.update(d)
            self._estado_seccion = d.get('estado_seccion', 'pendiente')
            # Convertir creado_en a datetime
            try:
                self.creado_en = datetime.fromisoformat(d['creado_en'])
            except:
                self.creado_en = datetime.now()
            # Convertir items a proxies
            self.items = [ItemProxy(i) for i in d.get('items', [])]

    class ItemProxy:
        def __init__(self, d):
            self.__dict__.update(d)
            if d.get('producto'):
                self.producto = ProductoProxy(d['producto'])
            else:
                self.producto = None

    class ProductoProxy:
        def __init__(self, d):
            self.__dict__.update(d)

    pedidos = [PedidoProxy(p) for p in pedidos_raw]
    now     = datetime.now()

    return render_template('chef/comandas.html',
        pedidos=pedidos,
        seccion=current_user.seccion,
        pendientes=len(pedidos),
        now=now,
    )

@chef_bp.route('/comandas/count')
@login_required
@solo_chef
def comandas_count():
    try:
        r    = requests.get(f'{API_URL}/chef/comandas/count', headers=api_headers())
        data = r.json()
        return jsonify({'count': data.get('count', 0)})
    except:
        return jsonify({'count': 0})

@chef_bp.route('/comandas/<int:pedido_id>/preparar', methods=['POST'])
@login_required
@solo_chef
def marcar_preparando(pedido_id):
    try:
        r    = requests.post(f'{API_URL}/chef/comandas/{pedido_id}/preparar', headers=api_headers())
        data = r.json()
        return jsonify(data), r.status_code
    except:
        return jsonify({'error': 'Error al conectar'}), 500

@chef_bp.route('/comandas/<int:pedido_id>/listo', methods=['POST'])
@login_required
@solo_chef
def marcar_listo(pedido_id):
    try:
        r    = requests.post(f'{API_URL}/chef/comandas/{pedido_id}/listo', headers=api_headers())
        data = r.json()
        return jsonify(data), r.status_code
    except:
        return jsonify({'error': 'Error al conectar'}), 500

@chef_bp.route('/comandas/<int:pedido_id>/entregar', methods=['POST'])
@login_required
@solo_chef
def marcar_entregado(pedido_id):
    try:
        r    = requests.post(f'{API_URL}/chef/escanear/{pedido_id}/entregar', headers=api_headers())
        data = r.json()
        return jsonify(data), r.status_code
    except:
        return jsonify({'error': 'Error al conectar'}), 500