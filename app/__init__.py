from datetime import datetime, date
from flask import Flask, render_template
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from app.config import Config
from app.models import db, User

login_manager = LoginManager()
csrf = CSRFProtect()

def create_app(config_class=Config):
    """Fábrica de aplicaciones Flask para Andiaseo."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Inicialización de extensiones
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth_bp.login'
    login_manager.login_message = 'Por favor inicia sesión para acceder al sistema de inventarios.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Filtros personalizados para plantillas Jinja2
    @app.template_filter('currency')
    def currency_filter(val):
        if val is None:
            return "$ 0.00"
        try:
            return f"$ {float(val):,.2f}"
        except (ValueError, TypeError):
            return "$ 0.00"

    @app.template_filter('number')
    def number_filter(val, decimals=2):
        if val is None:
            return "0.00"
        try:
            return f"{float(val):,.{decimals}f}"
        except (ValueError, TypeError):
            return "0.00"

    @app.template_filter('fecha')
    def fecha_filter(val, format='%d/%m/%Y'):
        if not val:
            return "-"
        if isinstance(val, (datetime, date)):
            return val.strftime(format)
        return str(val)

    # Inyección de variables globales a plantillas
    @app.context_processor
    def inject_globals():
        return {
            'ahora': datetime.now(),
            'app_name': 'Andiaseo - Control de Inventario Químico'
        }

    # Registro de Blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.inventory import inventory_bp
    from app.routes.lotes import lotes_bp
    from app.routes.produccion import produccion_bp
    from app.routes.reportes import reportes_bp
    from app.routes.documentos_ai import documentos_ai_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/')
    app.register_blueprint(inventory_bp, url_prefix='/inventario')
    app.register_blueprint(lotes_bp, url_prefix='/lotes')
    app.register_blueprint(produccion_bp, url_prefix='/produccion')
    app.register_blueprint(reportes_bp, url_prefix='/reportes')
    app.register_blueprint(documentos_ai_bp, url_prefix='/documentos-ai')

    # Manejadores de errores personalizados
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500

    return app
