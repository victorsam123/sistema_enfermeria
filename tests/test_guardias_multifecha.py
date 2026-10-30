import re
from datetime import date
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from flask_migrate import upgrade
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
import pytest
from app import create_app
from app.extensions import db
from app.models import Usuario
from app.models.administration import CambioGuardia, DetalleCambioGuardia, Justificativo
from app.administration.guardia_records import create_guardia
from app.services import initialize_admin
from test_auth import login

NORMAL = '/reposo/cambio-guardia/'
PAGADA = '/reposo/cambio-guardia-pagada/'
NAMES = {'solicitante': 'Gloria Ejemplo', 'reemplazante': 'Nora Ejemplo'}
DETAILS = [
    {'participante': 'S', 'fecha_guardia': '04/10/2026', 'hora_inicio': '18:00', 'hora_fin': '06:00', 'codigo': 'G'},
    {'participante': 'R', 'fecha_guardia': '05/10/2026', 'hora_inicio': '06:00', 'hora_fin': '12:00', 'codigo': 'L'},
]


@pytest.fixture(autouse=True)
def clean_multidate_test_records(app):
    with app.app_context():
        db.session.execute(db.delete(DetalleCambioGuardia))
        db.session.execute(db.delete(CambioGuardia))
        db.session.execute(db.delete(Justificativo))
        db.session.commit()
    yield
    with app.app_context():
        db.session.rollback()
        db.session.execute(db.delete(DetalleCambioGuardia))
        db.session.execute(db.delete(CambioGuardia))
        db.session.execute(db.delete(Justificativo))
        db.session.commit()


@pytest.fixture
def admin(client):
    assert login(client).status_code == 302
    return client


def form_data(client, path, names=NAMES, details=None):
    page = client.get(path)
    assert page.status_code == 200
    data = dict(names)
    data.setdefault('servicio_id', '1')
    for name in ('csrf_token', 'solicitud_id', 'version'):
        match = re.search(r'name="' + name + r'"[^>]*value="([^"]*)"', page.text)
        if match:
            data[name] = match.group(1)
    for index, detail in enumerate(details or DETAILS):
        for key, value in detail.items():
            data[f'detalles-{index}-{key}'] = value
    return data


@pytest.mark.parametrize('path', [NORMAL, PAGADA])
def test_different_dates_times_codes_and_navigation(app, admin, path):
    response = admin.post(path, data=form_data(admin, path), follow_redirects=True)
    assert response.status_code == 200
    assert '04/10/2026' in response.text and '05/10/2026' in response.text
    assert '18:00 a 06:00' in response.text and '06:00 a 12:00' in response.text
    assert re.search(r'href="/"[^>]*>.*?VOLVER AL PANEL PRINCIPAL', response.text, re.S)
    assert 'Volver a Reposo' not in response.text
    with app.app_context():
        row = db.session.scalar(db.select(CambioGuardia))
        assert row.tipo_cambio == ('NORMAL' if path == NORMAL else 'PAGADA')
        assert len(row.detalles) == 2
        assert [d.fecha_guardia for d in row.detalles] == [date(2026, 10, 4), date(2026, 10, 5)]
        assert [d.codigo for d in row.detalles] == ['G', 'L']
        assert row.detalles[0].fecha_fin == date(2026, 10, 5)
        assert row.usuario_registro.username == 'victor'
    assert admin.get('/').status_code == 200


def test_independent_multiple_dates_and_separate_operations(app, admin):
    details = [dict(DETAILS[0], fecha_guardia='02/10/2026'), dict(DETAILS[1], fecha_guardia='08/10/2026'),
               dict(DETAILS[0], fecha_guardia='17/10/2026', codigo='S')]
    assert admin.post(NORMAL, data=form_data(admin, NORMAL, details=details)).status_code == 303
    assert admin.post(NORMAL, data=form_data(admin, NORMAL, details=DETAILS)).status_code == 303
    with app.app_context():
        rows = db.session.scalars(db.select(CambioGuardia).order_by(CambioGuardia.id)).all()
        first_id, second_id = rows[0].id, rows[1].id
        assert len(rows[0].detalles) == 3 and len(rows[1].detalles) == 2
        assert {d.fecha_guardia.day for d in rows[0].detalles} == {2, 8, 17}
    page = admin.get(NORMAL).text
    assert page.count('data-cambio-id=') == 2
    assert f'data-cambio-id="{first_id}"' in page and f'data-cambio-id="{second_id}"' in page
    assert page.count('data-detalle-id=') == 5


def test_add_many_dates_above_old_request_limit(app, admin):
    details = [dict(DETAILS[index % 2], fecha_guardia=f'{index % 28 + 1:02}/10/{2026 + index // 28}') for index in range(120)]
    data = form_data(admin, NORMAL, details=details)
    from urllib.parse import urlencode
    assert len(urlencode(data).encode()) > 16 * 1024
    assert admin.post(NORMAL, data=data).status_code == 303
    with app.app_context():
        row = db.session.scalar(db.select(CambioGuardia))
        assert len(row.detalles) == 120
    # El límite general de los demás módulos permanece intacto.
    assert app.config['MAX_CONTENT_LENGTH'] == 16 * 1024


@pytest.mark.parametrize('path', [NORMAL, PAGADA])
def test_edit_add_dates_preserve_ids_creator_and_legacy_fields(app, admin, path):
    admin.post(path, data=form_data(admin, path))
    with app.app_context():
        row = db.session.scalar(db.select(CambioGuardia))
        rid, creator, creation = row.id, row.usuario_registro_id, row.fecha_creacion
        legacy = (row.fecha_cambio, row.hora_inicio, row.hora_fin)
        details = [dict(d, detalle_id=str(item.id)) for d, item in zip(DETAILS, row.detalles)]
        old_ids = {item.id for item in row.detalles}
    details[0]['fecha_guardia'] = '08/10/2026'
    details.append(dict(DETAILS[0], fecha_guardia='17/10/2026', codigo='R'))
    edit_url = f'{path}{rid}/editar'
    data = form_data(admin, edit_url, names={**NAMES, 'solicitante': 'Gloria Corregida'}, details=details)
    assert admin.post(edit_url, data=data).status_code == 303
    assert admin.post(edit_url, data=data).status_code == 409
    with app.app_context():
        row = db.session.get(CambioGuardia, rid)
        assert len(row.detalles) == 3 and old_ids.issubset({d.id for d in row.detalles})
        assert (row.fecha_cambio, row.hora_inicio, row.hora_fin) == legacy
        assert row.usuario_registro_id == creator and row.fecha_creacion == creation
        assert row.usuario_modificacion_id == creator and row.version == 2
        assert all(d.funcionario == 'Gloria Corregida' for d in row.detalles if d.participante == 'S')


def test_edit_rejects_foreign_or_missing_detail_ids(app, admin):
    admin.post(NORMAL, data=form_data(admin, NORMAL))
    with app.app_context():
        row = db.session.scalar(db.select(CambioGuardia))
        rid = row.id
        details = [dict(d, detalle_id=str(item.id)) for d, item in zip(DETAILS, row.detalles)]
    path = f'{NORMAL}{rid}/editar'
    tampered = [dict(details[0], detalle_id='99999999'), details[1]]
    assert admin.post(path, data=form_data(admin, path, details=tampered)).status_code == 409
    omitted = [dict(DETAILS[0]), details[1]]
    assert admin.post(path, data=form_data(admin, path, details=omitted)).status_code == 409
    with app.app_context():
        assert len(db.session.get(CambioGuardia, rid).detalles) == 2


@pytest.mark.parametrize('change', [
    {'fecha_guardia': '02-08/10/2026'}, {'fecha_guardia': ''}, {'fecha_guardia': '31/02/2026'},
    {'hora_inicio': '25:00'}, {'hora_fin': '18:00'}, {'codigo': 'X'}, {'participante': 'X'},
])
def test_invalid_detail_is_rejected_atomically(app, admin, change):
    details = [dict(DETAILS[0], **change), DETAILS[1]]
    assert admin.post(NORMAL, data=form_data(admin, NORMAL, details=details)).status_code == 422
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(CambioGuardia)) == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(DetalleCambioGuardia)) == 0


def test_duplicate_rows_and_repeat_submit(app, admin):
    duplicate = DETAILS + [dict(DETAILS[0])]
    assert admin.post(NORMAL, data=form_data(admin, NORMAL, details=duplicate)).status_code == 422
    data = form_data(admin, NORMAL)
    assert admin.post(NORMAL, data=data).status_code == 303
    assert admin.post(NORMAL, data=data).status_code == 303
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(CambioGuardia)) == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(DetalleCambioGuardia)) == 2


def test_search_any_detail_date_and_category_isolation(app, admin):
    admin.post(NORMAL, data=form_data(admin, NORMAL))
    admin.post(PAGADA, data=form_data(admin, PAGADA, names={'solicitante': 'Otro Solicitante', 'reemplazante': 'Otro Reemplazante'}))
    page = admin.get(NORMAL, query_string={'q': 'nora', 'desde': '05/10/2026', 'hasta': '05/10/2026'}).text
    assert 'Gloria Ejemplo' in page and '04/10/2026' in page and 'Otro Solicitante' not in page
    empty = admin.get(NORMAL, query_string={'desde': '06/10/2026', 'hasta': '06/10/2026'}).text
    assert 'Gloria Ejemplo' not in empty
    with app.app_context():
        rid = db.session.scalar(db.select(CambioGuardia.id).where(CambioGuardia.tipo_cambio == 'PAGADA'))
    assert admin.get(f'{NORMAL}{rid}/editar').status_code == 404


def test_edit_auth_csrf_and_role_control(app, admin):
    admin.post(NORMAL, data=form_data(admin, NORMAL))
    with app.app_context():
        rid = db.session.scalar(db.select(CambioGuardia.id))
    url = f'{NORMAL}{rid}/editar'
    assert admin.application.test_client().get(url).status_code == 302
    assert admin.post(url, data={}).status_code == 400
    assert admin.delete(url).status_code == 405


@pytest.mark.parametrize('coverage', ['', '22/10/2026'])
def test_justificativo_optional_coverage_create_and_edit(app, admin, coverage):
    path = '/justificativos/'
    page = admin.get(path)
    csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text).group(1)
    token = re.search(r'name="solicitud_id"[^>]*value="([^"]+)"', page.text).group(1)
    coverage_input = re.search(r'<input[^>]*id="fecha_cobertura"[^>]*>', page.text).group(0)
    assert 'required' not in coverage_input
    data = {'nombres_apellidos': 'Persona Justificativo', 'fecha_inasistencia': '21/10/2026',
            'servicio_id': '1',
            'motivo': 'Ausencia justificada', 'fecha_cobertura': coverage, 'csrf_token': csrf, 'solicitud_id': token}
    response = admin.post(path, data=data, follow_redirects=True)
    assert response.status_code == 200
    assert ('SIN COBERTURA' if not coverage else '22/10/2026') in response.text
    with app.app_context():
        row = db.session.scalar(db.select(Justificativo))
        rid = row.id
        assert row.fecha_cobertura == (date(2026, 10, 22) if coverage else None)
    edit = f'{path}{rid}/editar'
    page = admin.get(edit)
    version = re.search(r'name="version"[^>]*value="([^"]+)"', page.text).group(1)
    assert admin.post(edit, data={**data, 'version': version, 'fecha_cobertura': ''}).status_code == 303
    with app.app_context():
        assert db.session.get(Justificativo, rid).fecha_cobertura is None


def test_multidate_persistence_after_logout_and_new_app(app, admin):
    data = form_data(admin, NORMAL)
    admin.post(NORMAL, data=data)
    admin.post('/logout', data={'csrf_token': data['csrf_token']})
    assert admin.get(NORMAL).status_code == 302
    assert login(admin).status_code == 302
    assert '05/10/2026' in admin.get(NORMAL).text
    fresh = create_app({'TESTING': True, 'SECRET_KEY': app.secret_key,
        'SQLALCHEMY_DATABASE_URI': app.config['SQLALCHEMY_DATABASE_URI'], 'SESSION_COOKIE_SECURE': False})
    with fresh.app_context():
        assert len(db.session.scalar(db.select(CambioGuardia)).detalles) == 2


def test_concurrent_multidate_submission_is_atomic(app):
    from datetime import time
    details = [dict(detalle_id=None, participante=role, fecha_guardia=date(2026, 10, day),
        hora_inicio=time(18), hora_fin=time(6), codigo=None) for role, day in [('S', 4), ('R', 5)]]
    with app.app_context():
        uid = db.session.scalar(db.select(Usuario.id).where(Usuario.username == 'victor'))
    barrier, request_id = Barrier(2), str(uuid4())
    def submit():
        with app.app_context():
            barrier.wait(timeout=10)
            return create_guardia({**NAMES, 'tipo_cambio': 'NORMAL', 'servicio_id': 1}, details, uid, request_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert sorted(results) == [False, True]
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(DetalleCambioGuardia)) == 2


def test_migration_preserves_legacy_data_in_isolated_test_schema(app):
    schema = 'migracion6_' + uuid4().hex
    with app.app_context():
        assert make_url(app.config['SQLALCHEMY_DATABASE_URI']).database.endswith('_test')
        db.session.execute(db.text('CREATE SCHEMA ' + schema))
        db.session.commit()
    isolated = create_app({'TESTING': True, 'SECRET_KEY': app.secret_key,
        'SQLALCHEMY_DATABASE_URI': app.config['SQLALCHEMY_DATABASE_URI'], 'SESSION_COOKIE_SECURE': False,
        'SQLALCHEMY_ENGINE_OPTIONS': {'pool_pre_ping': True, 'connect_args': {'options': '-csearch_path=' + schema}}})
    with isolated.app_context():
        upgrade(revision='0004_reposos')
        from legacy_migration_helpers import legacy_admin
        uid = legacy_admin()
        for category in ('NORMAL', 'PAGADA'):
            db.session.execute(db.text('''INSERT INTO cambios_guardia
                (solicitante,reemplazante,fecha_cambio,hora_inicio,hora_fin,tipo_cambio,usuario_registro_id,solicitud_id)
                VALUES ('Persona Uno','Persona Dos','2026-10-04','18:00','06:00',:category,:uid,:request_id)'''),
                {'category': category, 'uid': uid, 'request_id': uuid4()})
        db.session.execute(db.text('''INSERT INTO justificativos
            (nombres_apellidos,fecha_inasistencia,motivo,fecha_cobertura,usuario_registro_id,solicitud_id)
            VALUES ('Persona Uno','2026-10-04','Motivo anterior','2026-10-08',:uid,:request_id)'''),
            {'uid': uid, 'request_id': uuid4()})
        db.session.commit()
        cols = 'id,solicitante,reemplazante,fecha_cambio,hora_inicio,hora_fin,tipo_cambio,usuario_registro_id,fecha_creacion,fecha_modificacion,solicitud_id'
        previous = db.session.execute(db.text('SELECT ' + cols + ' FROM cambios_guardia ORDER BY id')).all()
        db.session.remove()
        upgrade()
        assert db.session.execute(db.text('SELECT ' + cols + ' FROM cambios_guardia ORDER BY id')).all() == previous
        rows = db.session.scalars(db.select(CambioGuardia).order_by(CambioGuardia.id)).all()
        assert len(rows) == 2
        for row in rows:
            assert len(row.detalles) == 2
            assert [d.participante for d in row.detalles] == ['S', 'R']
            assert all(d.fecha_guardia == row.fecha_cambio and d.hora_inicio == row.hora_inicio and d.hora_fin == row.hora_fin for d in row.detalles)
        assert db.session.scalar(db.select(Justificativo)).fecha_cobertura == date(2026, 10, 8)
