from flask import Blueprint, render_template, jsonify, request
import requests

menu_bp = Blueprint('menu', __name__)

API_URL = 'https://tucafe-api-production.up.railway.app/api/v1'

@menu_bp.route('/')
def index():
    try:
        r          = requests.get(f'{API_URL}/productos/')
        data       = r.json()
        productos  = data.get('productos', [])
    except:
        productos  = []
    categorias = ['hamburguesas', 'pizza', 'tacos', 'sushi', 'postres']
    return render_template('index.html', productos=productos, categorias=categorias)

@menu_bp.route('/tienda')
def tienda():
    categoria = None
    q         = request.args.get('q', '').strip()
    params    = {}
    if q:
        params['q'] = q
    try:
        r         = requests.get(f'{API_URL}/productos/', params=params)
        data      = r.json()
        productos = data.get('productos', [])
    except:
        productos = []
    categorias = ['hamburguesas', 'pizza', 'tacos', 'sushi', 'postres']
    return render_template('tienda.html', productos=productos,
                           categorias=categorias, categoria=categoria, q=q)

@menu_bp.route('/tienda/<categoria>')
def tienda_categoria(categoria):
    q      = request.args.get('q', '').strip()
    params = {'categoria': categoria}
    if q:
        params['q'] = q
    try:
        r         = requests.get(f'{API_URL}/productos/', params=params)
        data      = r.json()
        productos = data.get('productos', [])
    except:
        productos = []
    categorias = ['hamburguesas', 'pizza', 'tacos', 'sushi', 'postres']
    return render_template('tienda.html', productos=productos,
                           categorias=categorias, categoria=categoria, q=q)

@menu_bp.route('/api/productos')
def api_productos():
    try:
        r    = requests.get(f'{API_URL}/productos/')
        data = r.json()
        return jsonify(data.get('productos', []))
    except:
        return jsonify([])