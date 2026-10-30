from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models import db, User

auth_bp = Blueprint('auth_bp', __name__)

def role_required(*allowed_roles):
    """Decorador para restringir el acceso según roles de usuario."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Debes iniciar sesión para acceder.', 'warning')
                return redirect(url_for('auth_bp.login'))
            if current_user.rol not in allowed_roles:
                flash('Acceso denegado: Tu rol no tiene permisos para esta acción.', 'danger')
                return redirect(url_for('dashboard_bp.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Inicio de sesión para operarios y administradores."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard_bp.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        if not username or not password:
            flash('Por favor ingresa usuario y contraseña.', 'danger')
            return render_template('auth/login.html')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if not user.activo:
                flash('Tu usuario se encuentra inactivo. Contacta al administrador.', 'danger')
                return render_template('auth/login.html')

            login_user(user, remember=remember)
            flash(f'¡Bienvenido/a, {user.nombre}! Has ingresado como {user.rol.capitalize()}.', 'success')
            
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('dashboard_bp.index'))
        else:
            flash('Usuario o contraseña incorrectos. Verifica tus credenciales.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Cierre de sesión seguro."""
    nombre = current_user.nombre
    logout_user()
    flash(f'Sesión cerrada correctamente. ¡Hasta pronto, {nombre}!', 'info')
    return redirect(url_for('auth_bp.login'))


@auth_bp.route('/usuarios')
@login_required
@role_required('admin')
def usuarios():
    """Gestión de usuarios del sistema (solo administradores)."""
    users = User.query.order_by(User.nombre.asc()).all()
    return render_template('auth/usuarios.html', users=users)


@auth_bp.route('/usuarios/nuevo', methods=['POST'])
@login_required
@role_required('admin')
def crear_usuario():
    """Creación de un nuevo usuario de bodega o administración."""
    username = request.form.get('username', '').strip()
    nombre = request.form.get('nombre', '').strip()
    password = request.form.get('password', '')
    rol = request.form.get('rol', 'almacenista')

    if not username or not nombre or not password:
        flash('Todos los campos son obligatorios.', 'danger')
        return redirect(url_for('auth_bp.usuarios'))

    if User.query.filter_by(username=username).first():
        flash(f'El nombre de usuario "{username}" ya existe.', 'warning')
        return redirect(url_for('auth_bp.usuarios'))

    nuevo_usuario = User(
        username=username,
        nombre=nombre,
        rol=rol,
        activo=True
    )
    nuevo_usuario.set_password(password)
    db.session.add(nuevo_usuario)
    db.session.commit()

    flash(f'Usuario "{username}" creado exitosamente.', 'success')
    return redirect(url_for('auth_bp.usuarios'))
