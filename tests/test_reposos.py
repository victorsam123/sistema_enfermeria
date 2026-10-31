import re
from datetime import date, datetime, timezone
from uuid import uuid4
from unittest.mock import patch
import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app import create_app
from app.extensions import db
from app.models import Usuario
from app.models.reposos import Reposo
from test_auth import login

URL = '/reposo/'
DATA = {'nombres_apellidos': 'Funcionario Ejemplo', 'fecha_desde': '01/10/2026',
        'fecha_hasta': '02/10/2026', 'diagnostico': 'Motivo de reposo de prueba',
        'fecha_entrega_departamento': '03/10/2026'}


@pytest.fixture(autouse=True)
def clean_rest_test_records(app):
    # El fixture principal exige una base exclusiva terminada en _test.
    with app.app_context():
        db.session.execute(db.delete(Reposo))
        db.session.commit()
    yield
    with app.app_context():
        db.session.rollback()
        db.session.execute(db.delete(Reposo))
        db.session.commit()


@pytest.fixture
def admin(client):
    assert login(client).status_code == 302
    return client


def payload(client, values, url=URL):
    page = client.get(url)
    assert page.status_code == 200
    result = dict(values)
    result.setdefault('servicio_id', '1')
    for name in ('csrf_token', 'solicitud_id', 'version'):
        match = re.search(r'name="' + name + r'"[^>]*value="([^"]*)"', page.text)
        if match:
            result[name] = match.group(1)
    return result


def test_rest_auth_csrf_and_preserved_guardia_access(client, admin):
    private = admin.application.test_client()
    assert private.get(URL).status_code == 302
    assert private.get(URL + '1/editar').status_code == 302
    assert admin.post(URL, data=DATA).status_code == 400
    html = admin.get(URL).text
    assert 'GUARDAR REPOSO' in html
    assert 'href="/reposo/cambios-guardia/"' in html
    assert 'href="/reposo/cambio-guardia-pagada/"' in html
    assert 'America/Asuncion' in html and 'Cerrar sesión' in html


@pytest.mark.parametrize('start,end,total', [
    ('01/10/2026', '02/10/2026', 2), ('16/10/2026', '29/10/2026', 14),
    ('01/10/2026', '01/10/2026', 1), ('28/02/2028', '01/03/2028', 3),
    ('31/12/2026', '01/01/2027', 2),
])
def test_rest_create_inclusive_days_and_audit(app, admin, start, end, total):
    values = {**DATA, 'fecha_desde': start, 'fecha_hasta': end,
              'total_dias': '99999', 'usuario_registro_id': '999999'}
    response = admin.post(URL, data=payload(admin, values), follow_redirects=True)
    assert response.status_code == 200
    assert 'Reposo registrado correctamente' in response.text
    assert 'value="Funcionario Ejemplo"' not in response.text
    with app.app_context():
        row = db.session.scalar(db.select(Reposo))
        assert row.total_dias == total and row.usuario_registro.username == 'victor'
        assert row.fecha_entrega_departamento == date(2026, 10, 3)
        assert row.fecha_creacion.tzinfo and row.fecha_modificacion.tzinfo


@pytest.mark.parametrize('change', [
    {'nombres_apellidos': '   '}, {'fecha_desde': ''}, {'fecha_hasta': ''},
    {'fecha_hasta': '30/09/2026'}, {'fecha_desde': '31/02/2026'},
    {'diagnostico': '  '}, {'diagnostico': 'x' * 2001},
    {'fecha_entrega_departamento': ''}, {'fecha_entrega_departamento': '31/02/2026'},
])
def test_rest_backend_validations(app, admin, change):
    data = payload(admin, DATA)
    response = admin.post(URL, data={**data, **change})
    assert response.status_code == 422
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Reposo)) == 0


def test_rest_edit_recalculates_and_preserves_creator(app, admin):
    admin.post(URL, data=payload(admin, DATA))
    with app.app_context():
        row = db.session.scalar(db.select(Reposo))
        rid, owner, created = row.id, row.usuario_registro_id, row.fecha_creacion
    url = f'{URL}{rid}/editar'
    assert 'value="2"' in admin.get(url).text
    data = payload(admin, {**DATA, 'fecha_hasta': '14/10/2026', 'total_dias': 'no-numérico'}, url)
    response = admin.post(url, data=data, follow_redirects=True)
    assert response.status_code == 200 and 'Reposo actualizado correctamente' in response.text
    assert admin.post(url, data={**data, 'fecha_hasta': '15/10/2026'}).status_code == 409
    with app.app_context():
        row = db.session.get(Reposo, rid)
        assert row.total_dias == 14 and row.version == 2
        assert row.usuario_registro_id == owner and row.fecha_creacion == created
        assert row.usuario_modificacion_id == owner and row.fecha_modificacion > created
    assert admin.delete(url).status_code == 405
    assert admin.post(f'{URL}{rid}/eliminar', data={'csrf_token': data['csrf_token']}).status_code == 404


def test_rest_search_overlap_sort_and_safe_rendering(admin):
    first = {**DATA, 'nombres_apellidos': 'Primera Persona', 'fecha_desde': '16/10/2026', 'fecha_hasta': '29/10/2026'}
    second = {**DATA, 'nombres_apellidos': 'Segunda Persona', 'diagnostico': '<script>alert(1)</script>'}
    admin.post(URL, data=payload(admin, first))
    admin.post(URL, data=payload(admin, second))
    filtered = admin.get(URL, query_string={'q': 'primera', 'desde': '20/10/2026', 'hasta': '20/10/2026'})
    assert 'Primera Persona' in filtered.text and 'Segunda Persona' not in filtered.text
    by_date = admin.get(URL, query_string={'orden': 'desde_asc'}).text
    by_creation = admin.get(URL, query_string={'orden': 'creacion_asc'}).text
    assert by_date.index('Segunda Persona') < by_date.index('Primera Persona')
    assert by_creation.index('Primera Persona') < by_creation.index('Segunda Persona')
    assert '&lt;script&gt;' in by_date and '<script>alert(1)</script>' not in by_date
    assert 'Primera Persona' not in admin.get(URL, query_string={'q': "' OR 1=1 --"}).text
    assert admin.get(URL, query_string={'orden': 'invalido'}).status_code == 400
    assert admin.get(URL, query_string={'desde': '21/10/2026', 'hasta': '20/10/2026'}).status_code == 400


def test_rest_pagination_retains_filters_and_order(app, admin):
    with app.app_context():
        user_id = db.session.scalar(db.select(Usuario.id).where(Usuario.username == 'victor'))
        for number in range(21):
            db.session.add(Reposo(nombres_apellidos=f'Persona Paginada {number:02}',
                servicio_id=1,
                fecha_desde=date(2026, 10, 1), fecha_hasta=date(2026, 10, 2), total_dias=2,
                diagnostico='Prueba de paginación', fecha_entrega_departamento=date(2026, 10, 3),
                usuario_registro_id=user_id, solicitud_id=uuid4()))
        db.session.commit()
    first = admin.get(URL, query_string={'q': 'Paginada', 'orden': 'creacion_asc'}).text
    assert 'Persona Paginada 00' in first and 'Persona Paginada 20' not in first
    assert 'page=2' in first and 'orden=creacion_asc' in first
    second = admin.get(URL, query_string={'q': 'Paginada', 'orden': 'creacion_asc', 'page': 2}).text
    assert 'Persona Paginada 20' in second and 'Persona Paginada 00' not in second


def test_rest_duplicate_prevention_allows_new_legitimate_record(app, admin):
    data = payload(admin, DATA)
    assert admin.post(URL, data=data).status_code == 303
    assert admin.post(URL, data=data).status_code == 303
    assert admin.post(URL, data={**data, 'diagnostico': 'Datos distintos con el mismo envío'}).status_code == 409
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Reposo)) == 1
    assert admin.post(URL, data=payload(admin, DATA)).status_code == 303
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Reposo)) == 2


def test_rest_persistence_after_logout_and_new_app(app, admin):
    data = payload(admin, DATA)
    admin.post(URL, data=data)
    admin.post('/logout', data={'csrf_token': data['csrf_token']})
    assert admin.get(URL).status_code == 302
    assert login(admin).status_code == 302
    assert DATA['diagnostico'] in admin.get(URL).text
    fresh = create_app({'TESTING': True, 'SECRET_KEY': app.secret_key,
        'SQLALCHEMY_DATABASE_URI': app.config['SQLALCHEMY_DATABASE_URI'], 'SESSION_COOKIE_SECURE': False})
    with fresh.app_context():
        row = db.session.scalar(db.select(Reposo))
        assert row.total_dias == 2 and row.diagnostico == DATA['diagnostico']


def test_rest_role_control(app, client):
    with app.app_context():
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'operador_test'))
        if not user:
            user = Usuario(nombre='Operador', username='operador_test', rol='OPERADOR', activo=True, debe_cambiar_password=False)
            db.session.add(user)
        user.set_password('clave-operador-test')
        db.session.commit()
    login(client, 'operador_test', 'clave-operador-test')
    assert client.get(URL).status_code == 200
    assert 'id="registros"' not in client.get(URL).text
    assert client.get(URL + '1/editar').status_code == 403


def test_rest_save_failure_preserves_form_without_logging_diagnosis(admin, caplog):
    data = payload(admin, DATA)
    with patch('app.administration.reposos.views.create_record', side_effect=SQLAlchemyError()):
        response = admin.post(URL, data=data)
    assert response.status_code == 503
    assert DATA['diagnostico'] in response.text and 'value="2"' in response.text
    assert DATA['diagnostico'] not in caplog.text


def test_rest_database_enforces_dates_and_calculated_days(app):
    with app.app_context():
        user_id = db.session.scalar(db.select(Usuario.id).where(Usuario.username == 'victor'))
        for start, end, total in [(date(2026, 10, 1), date(2026, 10, 2), 99),
                                  (date(2026, 10, 2), date(2026, 10, 1), 0)]:
            db.session.add(Reposo(nombres_apellidos='Prueba Restricción', fecha_desde=start,
                servicio_id=1,
                fecha_hasta=end, total_dias=total, diagnostico='Prueba',
                fecha_entrega_departamento=date(2026, 10, 3), usuario_registro_id=user_id, solicitud_id=uuid4()))
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()
