"""Intercambio y cupos en PostgreSQL real, sin tocar registros de producción."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from threading import Barrier
from uuid import uuid4
import re
import pytest
from app.extensions import db
from app.models import Usuario
from app.models.employees import Funcionario
from app.models.administration import CambioGuardia, DetalleCambioGuardia
from app.models.documents import DocumentoAdjunto
from app.administration.guardia_records import create_guardia
from app.administration.guardia_monthly import monthly_usage, GuardiaValidation
from test_auth import login
from test_guardias_multifecha import form_data

PATH = '/reposo/cambio-guardia-reemplazante/'
PAID = '/reposo/cambio-guardia-pagada/'
EMERGENCY = '/reposo/cambio-guardia-emergencia/'


@pytest.fixture
def people(app, tmp_path, monkeypatch):
    from app.documents.storage import LocalStorage
    monkeypatch.setitem(app.extensions, 'document_storage', LocalStorage(tmp_path / 'private-guardia'))
    with app.app_context():
        db.session.execute(db.delete(DocumentoAdjunto))
        db.session.execute(db.delete(DetalleCambioGuardia))
        db.session.execute(db.delete(CambioGuardia))
        uid = db.session.scalar(db.select(Usuario.id).where(Usuario.username == 'victor'))
        persons = []
        for index in range(4):
            person = Funcionario(nombres=f'Persona{index}', apellidos='Intercambio',
                cedula=str(800000000000 + int(uuid4().hex[:8], 16)), fecha_nacimiento=date(1990, 1, 1),
                fecha_ingreso=date(2020, 1, 1), direccion_actual='Dirección de prueba',
                servicio_id=1, usuario_registro_id=uid, solicitud_id=uuid4())
            db.session.add(person)
            persons.append(person)
        db.session.commit()
        result = [(p.id, p.nombre_completo) for p in persons]
    yield result
    with app.app_context():
        db.session.rollback()
        db.session.execute(db.delete(DocumentoAdjunto))
        db.session.execute(db.delete(DetalleCambioGuardia))
        db.session.execute(db.delete(CambioGuardia))
        db.session.execute(db.delete(Funcionario).where(Funcionario.id.in_([p[0] for p in result])))
        db.session.commit()


@pytest.fixture
def admin(client, people):
    assert login(client).status_code == 302
    return client


def names(people, first=0, second=1):
    return dict(solicitante=people[first][1], reemplazante=people[second][1],
        solicitante_funcionario_id=str(people[first][0]), reemplazante_funcionario_id=str(people[second][0]))


def details(day='31/10/2026', other='30/10/2026', start='06:00', end='12:00'):
    return [dict(participante=p, codigo=c, fecha_guardia=d, hora_inicio=s, hora_fin=e)
        for p, c, d, s, e in [('S', 'L', day, start, end), ('R', 'G', day, start, end),
            ('R', 'L', other, '12:00', '18:00'), ('S', 'G', other, '12:00', '18:00')]]


def submit(admin, people, rows=None, path=PATH, first=0, second=1, confirmed_advance=False):
    data = form_data(admin, path, names(people, first, second), rows or details())
    if confirmed_advance:
        data['confirmar_cupo_anticipado'] = '1'
    return admin.post(path, data=data)


def test_options_and_atomic_exchange_persist(app, admin, people):
    page = admin.get('/reposo/cambios-guardia/').text
    for path in (PATH, PAID, EMERGENCY):
        assert f'href="{path}"' in page
    response = submit(admin, people)
    assert response.status_code == 303
    page = admin.get(PATH).text
    assert 'contador mensual' in page and '1 de 2' in page
    assert '31/10/2026' in page and '30/10/2026' in page
    with app.app_context():
        record = db.session.scalar(db.select(CambioGuardia))
        assert len(record.detalles) == 4
        assert [(d.participante, d.codigo) for d in record.detalles] == [('S', 'L'), ('R', 'G'), ('R', 'L'), ('S', 'G')]
        rid = record.id
        for pid, name in people[:2]:
            assert monthly_usage(name, pid, date(2026, 10, 31)) == {'REEMPLAZO': 1, 'PAGADA': 0, 'EMERGENCIA': 0}
    assert admin.get(f'/registros/reemplazos/{rid}/imprimir').status_code == 200
    assert admin.get(f'/documentos/reemplazos/{rid}').status_code in (200, 308)


def test_independent_limits_and_both_participants(app, admin, people):
    assert submit(admin, people).status_code == 303
    assert submit(admin, people, details('24/10/2026', '23/10/2026')).status_code == 303
    result = submit(admin, people, details('17/10/2026', '16/10/2026'), first=2, second=1)
    assert result.status_code == 409 and people[1][1] in result.text and 'noviembre de 2026' in result.text
    assert submit(admin, people, details('17/10/2026', '16/10/2026'),
        first=2, second=1, confirmed_advance=True).status_code == 303
    assert submit(admin, people, path=PAID, rows=details()[:2]).status_code == 303
    assert submit(admin, people, path=PAID, rows=details('24/10/2026')[:2]).status_code == 409
    assert submit(admin, people, path=PAID, rows=details('24/10/2026')[:2], confirmed_advance=True).status_code == 303
    assert submit(admin, people, path=EMERGENCY, rows=details()[:2]).status_code == 303
    assert submit(admin, people, path=EMERGENCY, rows=details('24/10/2026')[:2]).status_code == 409
    assert submit(admin, people, path=EMERGENCY, rows=details('24/10/2026')[:2], confirmed_advance=True).status_code == 303
    with app.app_context():
        assert monthly_usage(people[0][1], people[0][0], date(2026, 10, 1)) == {'REEMPLAZO': 2, 'PAGADA': 1, 'EMERGENCIA': 1}
        assert monthly_usage(people[1][1], people[1][0], date(2026, 10, 1)) == {'REEMPLAZO': 2, 'PAGADA': 0, 'EMERGENCIA': 0}


def test_month_year_boundaries_cross_month_and_replay(app, admin, people):
    data = form_data(admin, PATH, names(people), details('31/12/2026', '01/01/2027', '18:00', '06:00'))
    assert admin.post(PATH, data=data).status_code == 303
    assert admin.post(PATH, data=data).status_code == 303
    with app.app_context():
        record = db.session.scalar(db.select(CambioGuardia))
        assert record.detalles[0].fecha_fin == date(2027, 1, 1)
        assert monthly_usage(people[0][1], people[0][0], date(2026, 12, 1))['REEMPLAZO'] == 1
        assert monthly_usage(people[0][1], people[0][0], date(2027, 1, 1))['REEMPLAZO'] == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(CambioGuardia)) == 1
    assert submit(admin, people, details('02/01/2027', '03/01/2027')).status_code == 303


@pytest.mark.parametrize('change', [
    {'hora_inicio': '07:00'}, {'hora_fin': '18:00'}, {'fecha_guardia': '31/02/2026'},
    {'codigo': 'G'}, {'participante': 'R'}, {'hora_inicio': ''}])
def test_invalid_exchange_rolls_back(app, admin, people, change):
    rows = details()
    rows[0].update(change)
    assert submit(admin, people, rows).status_code == 422
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(CambioGuardia)) == 0


@pytest.mark.parametrize('start,end', [('06:00', '12:00'), ('12:00', '18:00'), ('18:00', '06:00'), ('06:00', '18:00')])
def test_allowed_shift_lengths(admin, people, start, end):
    assert submit(admin, people, details(start=start, end=end)).status_code == 303


def test_weekday_twelve_hour_day_rejected(admin, people):
    assert submit(admin, people, details('29/10/2026', start='06:00', end='18:00')).status_code == 422


def test_missing_inverse_employee_and_duplicate(admin, people):
    assert submit(admin, people, details()[:2]).status_code == 422
    data = form_data(admin, PATH, names(people), details())
    data['reemplazante_funcionario_id'] = ''
    assert admin.post(PATH, data=data).status_code == 422
    assert submit(admin, people).status_code == 303
    result = submit(admin, people)
    assert result.status_code == 422 and 'ya está registrado' in result.text


def test_api_csrf_ticket_counts_and_month(app, admin, people):
    assert submit(admin, people).status_code == 303
    page = admin.get(PATH).text
    csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page).group(1)
    ticket = re.search(r'data-context="([^"]+)"', page).group(1)
    payload = dict(ticket=ticket, funcionario_id=people[0][0], fecha='31/10/2026', tipo_cambio='REEMPLAZO')
    url = '/reposo/cambios-guardia/control-mensual'
    assert admin.post(url, json=payload).status_code == 400
    response = admin.post(url, json=payload, headers={'X-CSRFToken': csrf})
    assert response.status_code == 200 and response.json['usados']['REEMPLAZO'] == 1
    assert response.json['disponibles']['REEMPLAZO'] == 1
    assert admin.post(url, json={**payload, 'ticket': 'invalido'}, headers={'X-CSRFToken': csrf}).status_code == 403
    assert admin.post(url, json={**payload, 'fecha': '31/02/2026'}, headers={'X-CSRFToken': csrf}).status_code == 422


def test_delete_releases_quota_restore_rechecks(app, admin, people):
    assert submit(admin, people, path=PAID, rows=details()[:2]).status_code == 303
    with app.app_context():
        record = db.session.scalar(db.select(CambioGuardia))
        rid, version = record.id, record.version
    delete_url = f'/registros/pagadas/{rid}/eliminar'
    csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', admin.get(delete_url).text).group(1)
    assert admin.post(delete_url, data=dict(csrf_token=csrf, version=version, confirmacion='CONFIRMAR', motivo='Cancelado administrativamente')).status_code == 303
    with app.app_context():
        assert monthly_usage(people[0][1], people[0][0], date(2026, 10, 1))['PAGADA'] == 0
        version = db.session.get(CambioGuardia, rid).version
    assert submit(admin, people, path=PAID, rows=details('24/10/2026')[:2]).status_code == 303
    response = admin.post(f'/registros/pagadas/{rid}/restaurar', data=dict(csrf_token=csrf, version=version), follow_redirects=True)
    assert 'ya no tiene cupo disponible' in response.text
    with app.app_context():
        assert db.session.get(CambioGuardia, rid).eliminado


def test_paid_requires_employee_and_enforces_individual_limit(app, admin, people):
    values = dict(solicitante=people[0][1], reemplazante='Otro Manual')
    assert admin.post(PAID, data=form_data(admin, PAID, values, details()[:2])).status_code == 422
    values['solicitante_funcionario_id'] = str(people[0][0])
    assert admin.post(PAID, data=form_data(admin, PAID, values, details()[:2])).status_code == 303
    assert admin.post(PAID, data=form_data(admin, PAID, values, details('24/10/2026')[:2])).status_code == 409
    assert admin.post(PAID, data={**form_data(admin, PAID, values, details('24/10/2026')[:2]),
        'confirmar_cupo_anticipado': '1'}).status_code == 303


def test_concurrent_different_submissions_cannot_exceed_limit(app, admin, people):
    assert submit(admin, people).status_code == 303
    barrier = Barrier(2)
    with app.app_context():
        uid = db.session.scalar(db.select(Usuario.id).where(Usuario.username == 'victor'))
    def save(index):
        with app.app_context():
            values = {**names(people, second=index + 1), 'servicio_id': 1, 'tipo_cambio': 'REEMPLAZO'}
            for role in ('solicitante', 'reemplazante'):
                values[role + '_funcionario_id'] = int(values[role + '_funcionario_id'])
            rows = [dict(detalle_id=None, participante=r['participante'], codigo=r['codigo'],
                fecha_guardia=date(2026, 10, 13 + index) if i < 2 else date(2026, 10, 12 + index),
                hora_inicio=time(6) if i < 2 else time(12), hora_fin=time(12) if i < 2 else time(18))
                for i, r in enumerate(details())]
            barrier.wait(timeout=10)
            try:
                return create_guardia(values, rows, uid, str(uuid4()))
            except GuardiaValidation:
                db.session.rollback()
                return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, (1, 2))) == [False, True]
    with app.app_context():
        assert monthly_usage(people[0][1], people[0][0], date(2026, 10, 1))['REEMPLAZO'] == 2
        assert db.session.scalar(db.select(db.func.count()).select_from(DetalleCambioGuardia)) == 8


def test_exchange_edit_preserves_ids_month_and_stale_version(app, admin, people):
    assert submit(admin, people).status_code == 303
    with app.app_context():
        record = db.session.scalar(db.select(CambioGuardia))
        rid, original_day = record.id, record.fecha_cambio
        rows = [dict(row, detalle_id=str(d.id)) for row, d in zip(details('24/10/2026', '23/10/2026'), record.detalles)]
        original_ids = {d.id for d in record.detalles}
    path = f'{PATH}{rid}/editar'
    data = form_data(admin, path, names(people), rows)
    assert admin.post(path, data=data).status_code == 303
    assert admin.post(path, data=data).status_code == 409
    with app.app_context():
        record = db.session.get(CambioGuardia, rid)
        assert {d.id for d in record.detalles} == original_ids
        assert record.fecha_cambio == original_day
        assert monthly_usage(people[0][1], people[0][0], original_day)['REEMPLAZO'] == 1


def test_exchange_attachments_and_export(app, admin, people):
    from io import BytesIO
    from PIL import Image
    from zipfile import ZipFile
    import xml.etree.ElementTree as ET
    photo = BytesIO()
    Image.new('RGB', (40, 40), 'blue').save(photo, 'PNG')
    photo.seek(0)
    data = form_data(admin, PATH, names(people), details())
    data['adjuntos_lote'] = str(uuid4())
    data['fotografias'] = (photo, 'respaldo.png')
    response = admin.post(PATH, data=data)
    assert response.status_code == 303, response.text
    with app.app_context():
        record = db.session.scalar(db.select(CambioGuardia))
        rid = record.id
        assert record.documentos_count == 1
        doc = db.session.scalar(db.select(DocumentoAdjunto))
        assert doc.tipo_modulo == 'reemplazos'
        did = doc.id
    assert admin.get(f'/documentos/reemplazos/{rid}/{did}/vista').status_code == 200
    assert admin.get(f'/documentos/guardias/{rid}/{did}/vista').status_code == 404
    data = form_data(admin, '/informes/', {}, details())
    data.update(desde='01/10/2026', hasta='31/10/2026', categoria='reemplazos', servicio_id='1', accion='descargar')
    response = admin.post('/informes/', data=data)
    assert response.status_code == 200
    with ZipFile(BytesIO(response.data)) as book:
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        workbook = ET.fromstring(book.read('xl/workbook.xml'))
        assert any(s.attrib['name'].endswith('_REEMPLAZOS') for s in workbook.findall('s:sheets/s:sheet', ns))
        strings = ET.fromstring(book.read('xl/sharedStrings.xml'))
        text = [''.join(node.itertext()) for node in strings]
        assert 'REEMPLAZO' in text
        sheet = ET.fromstring(book.read('xl/worksheets/sheet2.xml'))
        codes = [text[int(sheet.find(f'.//s:c[@r="K{row}"]/s:v', ns).text)] for row in range(8, 12)]
        assert codes == ['L', 'G', 'L', 'G']


def test_migration12_preserves_all_existing_rows_and_constraints(app):
    from flask_migrate import upgrade
    from app import create_app
    from app.services import initialize_admin
    schema = 'guardia12_' + uuid4().hex
    with app.app_context():
        db.session.execute(db.text('CREATE SCHEMA ' + schema))
        db.session.commit()
    isolated = create_app({'TESTING': True, 'SECRET_KEY': app.secret_key,
        'SQLALCHEMY_DATABASE_URI': app.config['SQLALCHEMY_DATABASE_URI'], 'SESSION_COOKIE_SECURE': False,
        'SQLALCHEMY_ENGINE_OPTIONS': {'connect_args': {'options': '-csearch_path=' + schema}}})
    with isolated.app_context():
        upgrade(revision='0011_carrera_funcionarios')
        initialize_admin()
        uid = db.session.scalar(db.select(Usuario.id).where(Usuario.username == 'victor'))
        for kind in ('NORMAL', 'PAGADA'):
            create_guardia(dict(solicitante='Histórico Uno', reemplazante='Histórico Dos', servicio_id=1, tipo_cambio=kind),
                [dict(detalle_id=None, participante=role, fecha_guardia=date(2026, 10, 31),
                    hora_inicio=time(18), hora_fin=time(6), codigo=role) for role in ('S', 'R')], uid, str(uuid4()))
        tables = ['usuarios', 'cambios_guardia', 'detalles_cambio_guardia', 'historial_administrativo', 'documentos_adjuntos']
        previous = {table: db.session.execute(db.text('SELECT * FROM ' + table + ' ORDER BY id')).all() for table in tables}
        db.session.remove()
        upgrade(revision='0012_guardias_intercambio')
        for table, original in previous.items():
            assert db.session.execute(db.text('SELECT * FROM ' + table + ' ORDER BY id')).all() == original
        assert db.session.scalar(db.text('SELECT version_num FROM alembic_version')) == '0012_guardias_intercambio'
