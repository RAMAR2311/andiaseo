import sys
import argparse
from app import create_app, db
from app.models import User

def crear_o_actualizar_admin(username, password, nombre):
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if user:
            user.nombre = nombre
            user.rol = 'admin'
            user.activo = True
            user.set_password(password)
            db.session.commit()
            print(f"[OK] Usuario '{username}' ya existía. Ha sido actualizado como Administrador con la nueva contraseña.")
        else:
            nuevo_admin = User(
                username=username,
                nombre=nombre,
                rol='admin',
                activo=True
            )
            nuevo_admin.set_password(password)
            db.session.add(nuevo_admin)
            db.session.commit()
            print(f"[OK] Usuario administrador '{username}' ({nombre}) creado exitosamente.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Crear o actualizar usuario Administrador en Andiaseo")
    parser.add_argument('--user', default='admin', help="Nombre de usuario (default: admin)")
    parser.add_argument('--password', required=True, help="Contraseña para el usuario")
    parser.add_argument('--nombre', default='Administrador del Sistema', help="Nombre completo")

    args = parser.parse_args()
    crear_o_actualizar_admin(args.user, args.password, args.nombre)

