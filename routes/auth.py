from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from models.usuario import Usuario
import requests

auth_bp = Blueprint('auth', __name__)

API_URL = 'http://localhost:5001/api/v1'

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('menu.index'))
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        try:
            r = requests.post(f'{API_URL}/auth/login', json={
                'email':    email,
                'password': password,
            })
            data = r.json()
            if r.status_code == 200 and data.get('ok'):
                # Guardar token en sesion
                session['jwt_token'] = data['token']
                # Cargar usuario de la BD local para flask-login
                usuario = Usuario.query.filter_by(email=email).first()
                if usuario:
                    login_user(usuario)
                if data['usuario']['rol'] == 'admin':
                    return redirect(url_for('admin.dashboard'))
                elif data['usuario']['rol'] == 'chef':
                    return redirect(url_for('chef.comandas'))
                return redirect(url_for('menu.tienda'))
            else:
                flash(data.get('error', 'Credenciales incorrectas'), 'error')
        except Exception as e:
            flash('Error al conectar con el servidor', 'error')
    return render_template('auth/login.html')

@auth_bp.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre   = request.form.get('nombre', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        try:
            r = requests.post(f'{API_URL}/auth/registro', json={
                'nombre':   nombre,
                'email':    email,
                'password': password,
            })
            data = r.json()
            if r.status_code == 201 and data.get('ok'):
                flash('Cuenta creada. Verifica tu correo.', 'success')
                return redirect(url_for('auth.verificar', email=email))
            else:
                flash(data.get('error', 'Error al registrar'), 'error')
        except Exception as e:
            flash('Error al conectar con el servidor', 'error')
    return render_template('auth/registro.html')

@auth_bp.route('/verificar', methods=['GET', 'POST'])
def verificar():
    email = request.args.get('email') or request.form.get('email', '')
    if request.method == 'POST':
        codigo  = request.form.get('codigo', '').strip()
        email   = request.form.get('email', '').strip()
        try:
            r = requests.post(f'{API_URL}/auth/verificar', json={
                'email':  email,
                'codigo': codigo,
            })
            data = r.json()
            if r.status_code == 200 and data.get('ok'):
                session['jwt_token'] = data['token']
                usuario = Usuario.query.filter_by(email=email).first()
                if usuario:
                    login_user(usuario)
                flash('Cuenta verificada. Bienvenido!', 'success')
                return redirect(url_for('menu.tienda'))
            else:
                flash(data.get('error', 'Codigo incorrecto'), 'error')
        except Exception as e:
            flash('Error al conectar con el servidor', 'error')
    return render_template('auth/verificar.html', email=email)

@auth_bp.route('/logout')
@login_required
def logout():
    session.pop('jwt_token', None)
    logout_user()
    return redirect(url_for('menu.index'))