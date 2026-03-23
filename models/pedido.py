from config.database import db
from datetime import datetime

class Pedido(db.Model):
    __tablename__ = 'pedidos'
    id           = db.Column(db.Integer, primary_key=True)
    usuario_id   = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    total        = db.Column(db.Numeric(10, 2), default=0)
    estado       = db.Column(db.String(20), default='pendiente')
    pagado       = db.Column(db.Boolean, default=False)
    notas        = db.Column(db.Text, nullable=True)
    metodo_pago  = db.Column(db.String(20), default='efectivo')
    notificacion = db.Column(db.Boolean, default=False)
    hora_recoger = db.Column(db.Time, nullable=True)
    archivado    = db.Column(db.Boolean, default=False)
    creado_en    = db.Column(db.DateTime, default=datetime.utcnow)
    items        = db.relationship('ItemPedido', backref='pedido', lazy=True)
    estados      = db.relationship('EstadoSeccion', backref='pedido', lazy=True)

    def turno(self):
        hora = self.creado_en.hour
        return 'matutino' if hora < 15 else 'vespertino'

    def calidad_vencida(self):
        if not self.hora_recoger:
            return False
        return datetime.now().time() > self.hora_recoger

class ItemPedido(db.Model):
    __tablename__ = 'items_pedido'
    id          = db.Column(db.Integer, primary_key=True)
    pedido_id   = db.Column(db.Integer, db.ForeignKey('pedidos.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    cantidad    = db.Column(db.Integer, nullable=False)
    precio_unit = db.Column(db.Numeric(10, 2), nullable=False)
    producto    = db.relationship('Producto', foreign_keys=[producto_id], lazy=True)

    def subtotal(self):
        return float(self.precio_unit) * self.cantidad

class EstadoSeccion(db.Model):
    __tablename__ = 'estados_seccion'
    id           = db.Column(db.Integer, primary_key=True)
    pedido_id    = db.Column(db.Integer, db.ForeignKey('pedidos.id'), nullable=False)
    seccion      = db.Column(db.String(50), nullable=False)
    estado       = db.Column(db.String(20), default='pendiente')
    notificacion = db.Column(db.Boolean, default=False)
    listo_en     = db.Column(db.DateTime, nullable=True)
    creado_en    = db.Column(db.DateTime, default=datetime.utcnow)