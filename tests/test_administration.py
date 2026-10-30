import re
from datetime import date, time
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
import pytest
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app import create_app
from app.extensions import db
from app.models import Usuario
from app.models.administration import Justificativo, CambioGuardia, DetalleCambioGuardia
from app.administration.services import create_record
from test_auth import login

JUST = '/justificativos/'
NORMAL = '/reposo/cambio-guardia/'
PAGADA = '/reposo/cambio-guardia-pagada/'
JUST_DATA = {'nombres_apellidos': 'Ana María López', 'fecha_inasistencia': '21/10/2026',
             'motivo': 'Trámite personal autorizado', 'fecha_cobertura': '22/10/2026'}
GUARD_DATA = {'solicitante': 'Ana María López', 'reemplazante': 'Luis González',
              'fecha_cambio': '21/10/2026', 'hora_inicio': '18:00', 'hora_fin': '06:00'}


@pytest.fixture(autouse=True)
def clean_administrative_test_records(app):
    # Solo se ejecuta en la base aislada que exige tests/conftest.py.
    with app.app_context():
        db.session.execute(db.delete(Justificativo))
        db.session.execute(db.delete(DetalleCambioGuardia))
        db.session.execute(db.delete(CambioGuardia))
        db.session.commit()
    yield
    with app.app_context():
        db.session.rollback()
        db.session.execute(db.delete(Justificativo))
        db.session.execute(db.delete(DetalleCambioGuardia))
        db.session.execute(db.delete(CambioGuardia))
        db.session.commit()


@pytest.fixture
def admin(client):
    assert login(client).status_code == 302
    return client


def form_values(client, url, values):
    page = client.get(url)
    assert page.status_code == 200
    result = dict(values)
    result.setdefault('servicio_id', '1')
    for field in ('csrf_token', 'solicitud_id', 'version'):
        match = re.search(r'name="' + field + r'"[^>]*value="([^"]*)"', page.text)
        if match:
            result[field] = match.group(1)
    return result


@pytest.mark.parametrize('path', [JUST, '/reposo/', NORMAL, PAGADA, '/justificativos/1/editar'])
def test_new_routes_require_authentication(client, path):
    assert client.get(path).status_code == 302


@pytest.mark.parametrize('path', [JUST, NORMAL, PAGADA])
def test_new_forms_require_csrf(admin, path):
    assert admin.post(path, data=JUST_DATA).status_code == 400


def test_justificativo_create_persist_clean_and_audit(app, admin):
    data = form_values(admin, JUST, {**JUST_DATA, 'usuario_registro_id': '999999'})
    response = admin.post(JUST, data=data, follow_redirects=True)
    assert response.status_code == 200
    assert 'Justificativo registrado correctamente' in response.text
    assert '21/10/2026' in response.text
    assert 'value="Ana María López"' not in response.text  # Formulario limpio tras PRG.
    with app.app_context():
        item = db.session.scalar(db.select(Justificativo))
        user_id = db.session.scalar(db.select(Usuario.id).where(Usuario.username == 'victor'))
        assert item.usuario_registro_id == user_id
        assert item.fecha_inasistencia == date(2026, 10, 21)
        assert item.fecha_cobertura == date(2026, 10, 22)
        assert item.fecha_creacion.tzinfo and item.fecha_modificacion.tzinfo
        record_id = item.id
    fresh = create_app({'TESTING': True, 'SECRET_KEY': app.secret_key,
                        'SQLALCHEMY_DATABASE_URI': app.config['SQLALCHEMY_DATABASE_URI'], 'SESSION_COOKIE_SECURE': False})
    with fresh.app_context():
        assert db.session.get(Justificativo, record_id).motivo == JUST_DATA['motivo']


def test_justificativo_edit_and_stale_submission(app, admin):
    admin.post(JUST, data=form_values(admin, JUST, JUST_DATA))
    with app.app_context():
        item = db.session.scalar(db.select(Justificativo))
        record_id, creator, creation = item.id, item.usuario_registro_id, item.fecha_creacion
    url = f'{JUST}{record_id}/editar'
    data = form_values(admin, url, {**JUST_DATA, 'motivo': 'Motivo corregido'})
    response = admin.post(url, data=data, follow_redirects=True)
    assert response.status_code == 200
    assert 'Justificativo actualizado correctamente' in response.text
    assert admin.post(url, data={**data, 'motivo': 'Edición obsoleta'}).status_code == 409
    with app.app_context():
        item = db.session.get(Justificativo, record_id)
        assert item.motivo == 'Motivo corregido'
        assert item.usuario_registro_id == creator and item.fecha_creacion == creation
        assert item.usuario_modificacion_id == creator
        assert item.fecha_modificacion > creation and item.version == 2
    assert admin.delete(url).status_code == 405
    assert admin.post(f'{JUST}{record_id}/eliminar', data={'csrf_token': data['csrf_token']}).status_code == 404


@pytest.mark.parametrize('change', [
    {'nombres_apellidos': '   '}, {'motivo': ''}, {'fecha_inasistencia': '31/02/2026'},
    {'fecha_cobertura': '31/02/2026'}, {'solicitud_id': 'no-uuid'}, {'motivo': 'x' * 2001},
])
def test_justificativo_backend_validates_every_field(app, admin, change):
    data = form_values(admin, JUST, JUST_DATA)
    assert admin.post(JUST, data={**data, **change}).status_code == 422
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Justificativo)) == 0


def test_justificativo_filters_and_safe_rendering(admin):
    admin.post(JUST, data=form_values(admin, JUST, JUST_DATA))
    other = {**JUST_DATA, 'nombres_apellidos': 'Carlos Ejemplo', 'fecha_inasistencia': '01/11/2026',
             'motivo': '<script>alert(1)</script>'}
    admin.post(JUST, data=form_values(admin, JUST, other))
    result = admin.get(JUST, query_string={'q': 'ana maría', 'desde': '21/10/2026', 'hasta': '21/10/2026'})
    assert 'Trámite personal autorizado' in result.text and 'Carlos Ejemplo' not in result.text
    assert 'Trámite personal autorizado' not in admin.get(JUST, query_string={'q': "' OR 1=1 --"}).text
    page = admin.get(JUST)
    assert '&lt;script&gt;' in page.text and '<script>alert(1)</script>' not in page.text
    assert admin.get(JUST, query_string={'desde': '22/10/2026', 'hasta': '21/10/2026'}).status_code == 400


def test_repeated_submission_and_legitimate_identical_record(app, admin):
    data = form_values(admin, JUST, JUST_DATA)
    assert admin.post(JUST, data=data).status_code == 303
    assert admin.post(JUST, data=data).status_code == 303
    assert admin.post(JUST, data={**data, 'motivo': 'Otros datos con el mismo token'}).status_code == 409
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Justificativo)) == 1
    assert admin.post(JUST, data=form_values(admin, JUST, JUST_DATA)).status_code == 303
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Justificativo)) == 2


def test_normal_paid_are_separate_and_support_overnight(app, admin):
    assert admin.post(NORMAL, data=form_values(admin, NORMAL, {**GUARD_DATA, 'tipo_cambio': 'PAGADA'})).status_code == 303
    paid_data = {**GUARD_DATA, 'solicitante': 'Solicitante Pagado', 'reemplazante': 'Reemplazante Pagado'}
    assert admin.post(PAGADA, data=form_values(admin, PAGADA, paid_data)).status_code == 303
    normal, paid = admin.get(NORMAL), admin.get(PAGADA)
    assert 'Ana María López' in normal.text and 'Solicitante Pagado' not in normal.text
    assert 'Solicitante Pagado' in paid.text and 'Ana María López' not in paid.text
    assert '18:00 a 06:00' in normal.text and '22/10/2026 (+1 día)' in normal.text
    with app.app_context():
        rows = db.session.scalars(db.select(CambioGuardia).order_by(CambioGuardia.id)).all()
        assert [row.tipo_cambio for row in rows] == ['NORMAL', 'PAGADA']
        assert rows[0].hora_inicio == time(18) and rows[0].hora_fin == time(6)
        assert rows[0].fecha_fin == date(2026, 10, 22)
        assert rows[0].usuario_registro.username == 'victor'


@pytest.mark.parametrize('change', [
    {'solicitante': ''}, {'reemplazante': '  ANA   MARÍA LÓPEZ  '},
    {'hora_inicio': '25:00'}, {'hora_fin': '18:00'}, {'hora_fin': ''}, {'fecha_cambio': 'invalida'},
])
def test_guardia_backend_validation(app, admin, change):
    data = form_values(admin, NORMAL, GUARD_DATA)
    assert admin.post(NORMAL, data={**data, **change}).status_code == 422
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(CambioGuardia)) == 0


def test_failed_save_retains_user_data(admin):
    data = form_values(admin, JUST, JUST_DATA)
    with patch('app.administration.justificativos.create_record', side_effect=SQLAlchemyError()):
        response = admin.post(JUST, data=data)
    assert response.status_code == 503
    assert 'No se pudo guardar el justificativo' in response.text
    assert 'Trámite personal autorizado' in response.text and 'value="Ana María López"' in response.text


def test_operator_cannot_access_new_modules(app, client):
    with app.app_context():
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'operador_test'))
        if not user:
            user = Usuario(username='operador_test', nombre='Operador', rol='OPERADOR', activo=True, debe_cambiar_password=False)
            db.session.add(user)
        user.set_password('clave-operador-test')
        db.session.commit()
    login(client, 'operador_test', 'clave-operador-test')
    for url in (JUST, '/reposo/', NORMAL, PAGADA):
        response = client.get(url)
        assert response.status_code == 200
        assert 'id="registros"' not in response.text
    assert client.get(JUST + '1/editar').status_code == 403


def test_concurrent_submission_creates_one_record(app):
    with app.app_context():
        user_id = db.session.scalar(db.select(Usuario.id).where(Usuario.username == 'victor'))
    request_id, barrier = str(uuid4()), Barrier(2)
    values = {'nombres_apellidos': 'Prueba Concurrente', 'fecha_inasistencia': date(2026, 10, 21),
              'servicio_id': 1,
              'fecha_cobertura': date(2026, 10, 22), 'motivo': 'Prueba de doble envío concurrente'}
    def submit():
        with app.app_context():
            barrier.wait(timeout=10)
            return create_record(Justificativo, values, user_id, request_id)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: submit(), range(2)))
    assert sorted(results) == [False, True]
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Justificativo)) == 1


def test_postgresql_rejects_invalid_guardia_category_and_same_people(app):
    with app.app_context():
        user_id = db.session.scalar(db.select(Usuario.id).where(Usuario.username == 'victor'))
        for category, replacement in [('OTRA', 'Persona Dos'), ('NORMAL', 'persona uno')]:
            row = CambioGuardia(solicitante='Persona Uno', reemplazante=replacement,
                servicio_id=1,
                fecha_cambio=date(2026, 10, 21), hora_inicio=time(7), hora_fin=time(13),
                tipo_cambio=category, usuario_registro_id=user_id, solicitud_id=uuid4())
            db.session.add(row)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()
