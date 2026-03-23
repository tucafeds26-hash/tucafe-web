from config.database import db
from datetime import datetime

class Producto(db.Model):
    __tablename__ = 'productos'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(255))
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    emoji = db.Column(db.String(10), default='🍽️')
    imagen = db.Column(db.String(255), nullable=True)
    disponible = db.Column(db.Boolean, default=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'precio': float(self.precio),
            'categoria': self.categoria,
            'emoji': self.emoji,
            'imagen': self.imagen,
            'disponible': self.disponible,
        }

    def __repr__(self):
        return f'<Producto {self.nombre}>'