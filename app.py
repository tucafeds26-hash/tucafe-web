from flask import Flask
from flask_login import LoginManager
from flask_mail import Mail
from models.usuario import Usuario
from config.database import db, init_db
from routes.auth import auth_bp
from routes.menu import menu_bp
from routes.pedidos import pedidos_bp
from routes.admin import admin_bp
from routes.chef import chef_bp

app = Flask(__name__)
app.config['SECRET_KEY']                     = 'tucafe-secret-2024'
app.config['SQLALCHEMY_DATABASE_URI']        = 'postgresql+psycopg2://postgres:12345@localhost:5432/tucafe'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['MAIL_SERVER']         = 'smtp.gmail.com'
app.config['MAIL_PORT']           = 587
app.config['MAIL_USE_TLS']        = True
app.config['MAIL_USERNAME']       = 'tucafeds26@gmail.com'
app.config['MAIL_PASSWORD']       = 'fexx lfbq ypro rjwk'
app.config['MAIL_DEFAULT_SENDER'] = 'tucafeds26@gmail.com'

db.init_app(app)
mail = Mail(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view     = 'auth.login'
login_manager.login_message  = 'Inicia sesion para continuar'
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

app.register_blueprint(auth_bp,    url_prefix='/auth')
app.register_blueprint(menu_bp,    url_prefix='/')
app.register_blueprint(pedidos_bp, url_prefix='/pedidos')
app.register_blueprint(admin_bp,   url_prefix='/admin')
app.register_blueprint(chef_bp,    url_prefix='/chef')

with app.app_context():
    db.create_all()
    init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)