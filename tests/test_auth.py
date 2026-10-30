import re
import pytest
from sqlalchemy.exc import DBAPIError
from app import create_app
from app.extensions import db
from app.models import Usuario, LogAcceso
from app.services import initialize_admin


def token(client):
    page = client.get('/login')
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text).group(1)


def login(client, username='victor', password='513625'):
    return client.post('/login', data={'username': username, 'password': password, 'csrf_token': token(client)})


def test_restricted_dashboard(client):
    result = client.get('/')
    assert result.status_code == 302
    assert '/login' in result.location
    assert client.get('/api/reloj').status_code == 302


def test_login_logout_and_audit(app, client):
    assert login(client).status_code == 302
    page = client.get('/')
    assert page.status_code == 200
    assert 'Conectada' in page.text
    assert 'Superadministrador' in page.text
    for label in ('Justificativo', 'Reposo', 'Cambio de Guardia', 'Vacaciones', 'Comisionados'):
        assert label in page.text
    assert page.text.count('data-module=') == 0
    for path in ('/justificativos/', '/reposo/', '/reposo/cambio-guardia/', '/vacaciones/', '/comisionados/'):
        assert f'href="{path}"' in page.text
    assert 'America/Asuncion' in page.text
    assert re.search(r'id="dashboard-date"[^>]*>\d{2}/\d{2}/\d{4}</time>', page.text)
    assert re.search(r'id="dashboard-time"[^>]*>\d{2}:\d{2}:\d{2}</time>', page.text)
    clock = client.get('/api/reloj')
    assert clock.status_code == 200
    assert clock.json['timezone'] == 'America/Asuncion'
    assert isinstance(clock.json['epoch_ms'], int)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    assert client.get('/logout').status_code == 405
    assert client.post('/logout', data={'csrf_token': csrf}).status_code == 302
    assert client.get('/').status_code == 302
    with app.app_context():
        events = db.session.scalars(db.select(LogAcceso.tipo_evento)).all()
        assert 'login_exitoso' in events and 'logout' in events
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'victor'))
        assert user.ultimo_acceso is not None


def test_generic_error(client):
    first = login(client, password='incorrecta')
    second = login(client, username='desconocido')
    assert first.status_code == second.status_code == 401
    message = 'Credenciales incorrectas. Verifica tus datos e inténtalo nuevamente.'
    assert message in first.text and message in second.text


def test_csrf(client):
    assert client.post('/login', data={'username': 'victor', 'password': '513625'}).status_code == 400


def test_rate_limit(client):
    for _ in range(5):
        assert login(client, password='incorrecta').status_code == 401
    assert login(client).status_code == 429


def test_idempotent_init_and_password_persistence(app):
    with app.app_context():
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'victor'))
        user.set_password('nueva-clave-segura')
        db.session.commit()
        original_id, original_hash = user.id, user.password_hash
        assert original_hash != 'nueva-clave-segura'
        assert not initialize_admin()
        assert db.session.scalar(db.select(db.func.count()).select_from(Usuario).where(Usuario.username == 'victor')) == 1
    fresh = create_app({'TESTING': True, 'SECRET_KEY': app.secret_key,
                        'SQLALCHEMY_DATABASE_URI': app.config['SQLALCHEMY_DATABASE_URI'], 'SESSION_COOKIE_SECURE': False})
    with fresh.app_context():
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'victor'))
        assert user.id == original_id and user.password_hash == original_hash
        assert user.check_password('nueva-clave-segura')


@pytest.mark.parametrize('statement', [
    "DELETE FROM usuarios WHERE username='victor'",
    "UPDATE usuarios SET activo=false WHERE username='victor'",
    "UPDATE usuarios SET protegido=false WHERE username='victor'",
    "UPDATE usuarios SET username='otro' WHERE username='victor'",
    "UPDATE usuarios SET rol='Administrador' WHERE username='victor'",
    'TRUNCATE usuarios CASCADE',
])
def test_postgres_protects_victor(app, statement):
    with app.app_context():
        with pytest.raises(DBAPIError):
            db.session.execute(db.text(statement))
            db.session.commit()
        db.session.rollback()
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'victor'))
        assert user.activo and user.protegido and user.rol == 'SUPERADMIN'


def test_python_protects_victor(app):
    with app.app_context():
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'victor'))
        db.session.delete(user)
        with pytest.raises(ValueError):
            db.session.commit()
        db.session.rollback()
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'victor'))
        user.activo = False
        with pytest.raises(ValueError):
            db.session.commit()
        db.session.rollback()


def test_role_restriction(app, client):
    with app.app_context():
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'operador_test'))
        if not user:
            user = Usuario(nombre='Operador', username='operador_test', rol='OPERADOR', activo=True, debe_cambiar_password=False)
            db.session.add(user)
        user.set_password('clave-operador-test')
        db.session.commit()
    assert login(client, 'operador_test', 'clave-operador-test').status_code == 302
    assert client.get('/').status_code == 200
    assert client.get('/api/reloj').status_code == 200
    assert 'Gestión de Usuarios' not in client.get('/').text
    assert client.get('/usuarios/').status_code == 403


def test_password_change_invalidates_session(app, client):
    assert login(client).status_code == 302
    result = app.test_cli_runner().invoke(args=['change-admin-password', '--password', 'nueva-clave-12345'])
    assert result.exit_code == 0
    assert client.get('/').status_code == 302


def test_security_headers(client):
    response = client.get('/login')
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['Cache-Control'] == 'no-store'
    assert "form-action 'self'" in response.headers['Content-Security-Policy']
