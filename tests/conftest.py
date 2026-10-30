"""Pruebas de integración reales. Exige una base vacía terminada en _test.

Nunca usa SQLite ni elimina tablas o bases de datos.
"""
import os
import pytest
from sqlalchemy.engine import make_url
from flask_migrate import upgrade
from app import create_app
from app.extensions import db
from app.models import Usuario, IntentoLogin, LogAcceso
from app.services import initialize_admin


@pytest.fixture(scope='session')
def app():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Define TEST_DATABASE_URL apuntando a una base PostgreSQL de pruebas.')
    if not make_url(url).database.endswith('_test'):
        raise RuntimeError('La base de pruebas debe terminar en _test.')
    os.environ['INITIAL_ADMIN_PASSWORD'] = '513625'
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': url,
                      'SECRET_KEY': 'test-key-only-' + 'a' * 40, 'SESSION_COOKIE_SECURE': False})
    with app.app_context():
        upgrade()
        initialize_admin()
    yield app


@pytest.fixture(autouse=True)
def clean_counters(app):
    with app.app_context():
        db.session.execute(db.delete(IntentoLogin))
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'victor'))
        user.set_password('513625')
        db.session.commit()
    yield
    with app.app_context():
        db.session.rollback()
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()
