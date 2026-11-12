from pathlib import Path
import click
from dotenv import load_dotenv
from flask import Flask, render_template, session
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_wtf.csrf import CSRFError
from app.extensions import db, login_manager, migrate, csrf


def create_app(test_config=None):
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    # Config se importa antes de cargar .env: reconstruir sus valores ambientales.
    import importlib
    import config
    importlib.reload(config)
    app = Flask(__name__)
    app.config.from_object(config.Config)
    if test_config:
        app.config.update(test_config)
    if not app.config['SECRET_KEY'] or len(app.config['SECRET_KEY']) < 32:
        raise RuntimeError('SECRET_KEY debe contener al menos 32 caracteres aleatorios en .env.')
    if not app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql+psycopg://'):
        raise RuntimeError('Configura DATABASE_URL con una conexión PostgreSQL real.')
    if app.config['PRODUCTION'] and not app.config['SESSION_COOKIE_SECURE']:
        raise RuntimeError('En producción las cookies deben usar HTTPS.')
    if app.config['TRUST_PROXY']:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Inicia sesión para continuar.'
    login_manager.session_protection = 'strong'
    migrate.init_app(app, db, compare_type=True)
    csrf.init_app(app)
    from app.models import Usuario
    from app.routes.auth import bp as auth_bp
    from app.routes.main import bp as main_bp
    from app.novedades import bp as novedades_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(novedades_bp)
    from app.administration import register_administration
    register_administration(app)
    from app.documents import configure_documents
    configure_documents(app)
    from app.employees import configure_employees
    configure_employees(app)
    from app.security.first_access import configure_first_access
    configure_first_access(app)
    from app.security.permissions import can
    app.jinja_env.globals['can'] = can

    @app.context_processor
    def authorization_context():
        from app.security.permissions import can
        return {'can': can}

    @login_manager.user_loader
    def load_user(user_id):
        if not user_id.isdecimal():
            return None
        user = db.session.get(Usuario, int(user_id))
        from app.services import session_fingerprint
        import hmac
        return user if (user and user.activo and hmac.compare_digest(
            session.get('credential_version', ''), session_fingerprint(user))) else None

    @app.cli.command('init-admin')
    def init_admin():
        from app.services import initialize_admin
        created = initialize_admin()
        click.echo('Administrador creado.' if created else 'Administrador existente conservado sin cambios.')

    @app.cli.command('change-admin-password')
    @click.password_option(confirmation_prompt=True)
    def change_password(password):
        """Cambio seguro local; invalida las sesiones de la contraseña anterior."""
        if len(password) < 12:
            raise click.ClickException('Utiliza al menos 12 caracteres.')
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'victor'))
        if not user:
            raise click.ClickException('Primero inicializa el administrador.')
        user.set_password(password)
        user.debe_cambiar_password = False
        from app.security.user_operations import user_audit
        user_audit(user, 'PASSWORD_CAMBIADO', 'Contraseña actualizada mediante el procedimiento local autorizado.', actor_id=user.id)
        db.session.commit()
        click.echo('Contraseña actualizada. Las sesiones anteriores han sido invalidadas.')

    @app.after_request
    def security_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; font-src 'self'; img-src 'self' data: blob:; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
        if app.config['PRODUCTION']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return render_template('error.html', title='Formulario vencido', message='Recarga la página y vuelve a intentarlo.'), 400

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        db.session.rollback()
        app.logger.error('Error de disponibilidad de base de datos (%s)', type(error).__name__)
        return render_template('error.html', title='Servicio temporalmente no disponible', message='No se pudo completar la conexión a la base de datos. Inténtalo más tarde.'), 503

    for code, title in [(403, 'Acceso restringido'), (404, 'Página no encontrada'), (500, 'Error del sistema')]:
        def handler(error, title=title, code=code):
            db.session.rollback()
            message = 'No tiene permisos para realizar esta operación' if code == 403 else 'Regresa al inicio para continuar.'
            return render_template('error.html', title=title, message=message), code
        app.register_error_handler(code, handler)
    return app
