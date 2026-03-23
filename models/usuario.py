from config.database import db
from flask_login import UserMixin
from datetime import datetime

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id             = db.Column(db.Integer, primary_key=True)
    nombre         = db.Column(db.String(100), nullable=False)
    email          = db.Column(db.String(150), unique=True, nullable=False)
    password       = db.Column(db.String(255), nullable=False)
    rol            = db.Column(db.String(20), nullable=False, default='cliente')
    seccion        = db.Column(db.String(50), nullable=True)
    verificado     = db.Column(db.Boolean, default=False)
    codigo_ver     = db.Column(db.String(6), nullable=True)
    creado_en      = db.Column(db.DateTime, default=datetime.utcnow)
    pedidos        = db.relationship('Pedido', backref='cliente', lazy=True)

    def es_admin(self): return self.rol == 'admin'
    def es_chef(self):  return self.rol == 'chef'