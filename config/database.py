from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def init_db():
    """Inserta productos y usuario admin si la BD está vacía."""
    from models.usuario import Usuario
    from models.producto import Producto
    from werkzeug.security import generate_password_hash

    # ── Admin por defecto ────────────────────────────────────
    if not Usuario.query.filter_by(rol='admin').first():
        admin = Usuario(
            nombre='Admin',
            email='admin@tucafe.com',
            password=generate_password_hash('admin123'),
            rol='admin'
        )
        db.session.add(admin)

    # ── Chefs por defecto ────────────────────────────────────
    chefs = [
        ('Chef Burgers',  'chef_burger@tucafe.com',  'burger1',  'chef', 'hamburguesas'),
        ('Chef Pizza',    'chef_pizza@tucafe.com',   'pizza1',   'chef', 'pizza'),
        ('Chef Tacos',    'chef_tacos@tucafe.com',   'tacos1',   'chef', 'tacos'),
        ('Chef Sushi',    'chef_sushi@tucafe.com',   'sushi1',   'chef', 'sushi'),
        ('Chef Postres',  'chef_postres@tucafe.com', 'postres1', 'chef', 'postres'),
    ]
    for nombre, email, pwd, rol, seccion in chefs:
        if not Usuario.query.filter_by(email=email).first():
            db.session.add(Usuario(
                nombre=nombre, email=email,
                password=generate_password_hash(pwd),
                rol=rol, seccion=seccion
            ))

    # ── Productos iniciales ──────────────────────────────────
    if not Producto.query.first():
        productos = [
            # Hamburguesas
            ('Burger Clásica',  'Carne jugosa con queso cheddar',        89,  'hamburguesas', '🍔'),
            ('Burger Doble',    'Doble carne, doble sabor',               129, 'hamburguesas', '🍔'),
            ('Burger BBQ',      'Con salsa BBQ ahumada',                  99,  'hamburguesas', '🍔'),
            ('Burger Vegana',   '100% plant-based',                       95,  'hamburguesas', '🥗'),
            # Pizza
            ('Pizza Pepperoni', 'Con extra pepperoni y queso',            119, 'pizza',        '🍕'),
            ('Pizza Hawaiana',  'Jamón y piña caramelizada',              109, 'pizza',        '🍕'),
            ('Pizza 4 Quesos',  'Mozzarella, gouda, brie y parmesano',    125, 'pizza',        '🍕'),
            ('Pizza Vegetal',   'Sin carne, llena de verduras',           105, 'pizza',        '🍕'),
            # Tacos
            ('Taco de Birria',  'Con consomé para remojar',               65,  'tacos',        '🌮'),
            ('Taco de Pastor',  'Adobo y piña asada',                     55,  'tacos',        '🌮'),
            ('Taco de Suadero', 'Carne suave y jugosa',                   60,  'tacos',        '🌮'),
            ('Quesabirria',     'Tortilla frita con queso y birria',      85,  'tacos',        '🌮'),
            # Sushi
            ('Roll Especial',   'Salmón, aguacate y pepino',              145, 'sushi',        '🍱'),
            ('Nigiri de Atún',  'Atún fresco sobre arroz',                120, 'sushi',        '🍣'),
            ('Spicy Tuna Roll', 'Atún picante y sriracha',                135, 'sushi',        '🍱'),
            ('Dragon Roll',     'Camarón tempura y aguacate',             155, 'sushi',        '🍱'),
            # Postres
            ('Cheesecake NY',   'Relleno de frutos rojos',                75,  'postres',      '🍰'),
            ('Brownie Caliente','Con helado de vainilla',                  65,  'postres',      '🍫'),
            ('Churros',         'Crujientes bañados en chocolate',        55,  'postres',      '🧇'),
            ('Gelatina Mosaico','Colorida y cremosa',                     45,  'postres',      '🍮'),
        ]
        for nombre, desc, precio, categoria, emoji in productos:
            db.session.add(Producto(
                nombre=nombre, descripcion=desc,
                precio=precio, categoria=categoria,
                emoji=emoji, disponible=True
            ))

    db.session.commit()
