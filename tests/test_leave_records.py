import re
from datetime import date
from io import BytesIO
from uuid import uuid4
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET
import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app import create_app
from app.extensions import db
from app.models import Usuario
from app.models.employees import Funcionario
from app.models.leave_records import Comisionado, Vacacion
from app.employees.services import create_employee
from app.employees.employment_services import add_link
from test_auth import login

COM = '/comisionados/'
VAC = '/vacaciones/'
COM_DATA = {'nombres_apellidos': 'Ana Ejemplo', 'fecha_inasistencia': '21/10/2026',
            'motivo': 'Comisión institucional', 'lugar': 'Ciudad del Este'}
VAC_DATA = {'nombres_apellidos': 'Ana Ejemplo', 'fecha_inicio': '01/11/2026', 'fecha_termino': '15/11/2026'}


@pytest.fixture(autouse=True)
def clean_leave_test_records(app):
    # La factoría de pruebas exige una base _test; no limpia la base de la aplicación.
    with app.app_context():
        db.session.execute(db.delete(Comisionado))
        db.session.execute(db.delete(Vacacion))
        db.session.commit()
        employee = db.session.scalar(db.select(Funcionario).where(Funcionario.cedula == '99887766'))
        if employee is None:
            user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'victor'))
            create_employee({
                'nombres': 'Ana', 'apellidos': 'Ejemplo', 'cedula': '99887766',
                'carrera': 'LIC. EN ENFERMERIA', 'fecha_nacimiento': date(1990, 5, 15),
                'fecha_ingreso': date(2015, 3, 10), 'direccion_actual': 'Domicilio de prueba',
                'servicio_id': 1,
            }, [], str(uuid4()), user.id)
            db.session.commit()
        else:
            employee.carrera = 'LIC. EN ENFERMERIA'
            db.session.commit()
    yield
    with app.app_context():
        db.session.rollback()
        db.session.execute(db.delete(Comisionado))
        db.session.execute(db.delete(Vacacion))
        db.session.commit()


@pytest.fixture
def admin(client):
    assert login(client).status_code == 302
    return client


def form_values(client, url, values):
    page = client.get(url)
    assert page.status_code == 200
    data = dict(values)
    data.setdefault('servicio_id', '1')
    if url.startswith(VAC):
        with client.application.app_context():
            employee = db.session.scalar(db.select(Funcionario).where(Funcionario.cedula == '99887766'))
            data.setdefault('funcionario_id', str(employee.id))
    for name in ('csrf_token', 'solicitud_id', 'version'):
        field = re.search(r'name="' + name + r'"[^>]*value="([^"]*)"', page.text)
        if field:
            data[name] = field.group(1)
    return data


@pytest.mark.parametrize('path', [COM, VAC, COM + '1/editar', VAC + '1/editar'])
def test_leave_routes_require_authentication(client, path):
    assert client.get(path).status_code == 302


@pytest.mark.parametrize('path,data', [(COM, COM_DATA), (VAC, VAC_DATA)])
def test_leave_forms_require_csrf(admin, path, data):
    assert admin.post(path, data=data).status_code == 400


def test_comisionado_create_audit_and_clean_form(app, admin):
    data = form_values(admin, COM, {**COM_DATA, 'usuario_registro_id': '999999'})
    response = admin.post(COM, data=data, follow_redirects=True)
    assert response.status_code == 200
    assert 'Comisionado registrado correctamente' in response.text
    assert 'Ciudad del Este' in response.text and '21/10/2026' in response.text
    assert 'value="Ana Ejemplo"' not in response.text
    with app.app_context():
        row = db.session.scalar(db.select(Comisionado))
        assert row.nombres_apellidos == 'Ana Ejemplo'
        assert row.fecha_inasistencia == date(2026, 10, 21)
        assert row.usuario_registro.username == 'victor'
        assert row.fecha_creacion.tzinfo and row.fecha_modificacion.tzinfo


@pytest.mark.parametrize('change', [
    {'nombres_apellidos': ''}, {'fecha_inasistencia': ''}, {'fecha_inasistencia': '31/02/2026'},
    {'motivo': '   '}, {'lugar': '   '}, {'motivo': 'x' * 2001}, {'lugar': 'x' * 251},
])
def test_comisionado_backend_validation(app, admin, change):
    data = form_values(admin, COM, COM_DATA)
    assert admin.post(COM, data={**data, **change}).status_code == 422
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Comisionado)) == 0


def test_comisionado_edit_and_concurrent_edit_protection(app, admin):
    admin.post(COM, data=form_values(admin, COM, COM_DATA))
    with app.app_context():
        row = db.session.scalar(db.select(Comisionado))
        rid, creator, created = row.id, row.usuario_registro_id, row.fecha_creacion
    url = f'{COM}{rid}/editar'
    data = form_values(admin, url, {**COM_DATA, 'lugar': 'Asunción'})
    assert admin.post(url, data=data).status_code == 303
    assert admin.post(url, data={**data, 'lugar': 'Edición obsoleta'}).status_code == 409
    with app.app_context():
        row = db.session.get(Comisionado, rid)
        assert row.lugar == 'Asunción' and row.version == 2
        assert row.usuario_registro_id == creator and row.fecha_creacion == created
        assert row.usuario_modificacion_id == creator and row.fecha_modificacion > created


def test_comisionado_search_dates_sort_and_escaping(admin):
    admin.post(COM, data=form_values(admin, COM, COM_DATA))
    other = {**COM_DATA, 'nombres_apellidos': 'Carlos Ejemplo', 'fecha_inasistencia': '01/11/2026', 'lugar': '<script>alert(1)</script>'}
    admin.post(COM, data=form_values(admin, COM, other))
    filtered = admin.get(COM, query_string={'q': 'ana', 'desde': '21/10/2026', 'hasta': '21/10/2026'})
    assert 'Ana Ejemplo' in filtered.text and 'Carlos Ejemplo' not in filtered.text
    ascending = admin.get(COM, query_string={'orden': 'asc'}).text
    descending = admin.get(COM).text
    assert ascending.index('Ana Ejemplo') < ascending.index('Carlos Ejemplo')
    assert descending.index('Carlos Ejemplo') < descending.index('Ana Ejemplo')
    assert '&lt;script&gt;' in descending and '<script>alert(1)</script>' not in descending
    assert 'Ana Ejemplo' not in admin.get(COM, query_string={'q': "' OR 1=1 --"}).text
    assert admin.get(COM, query_string={'desde': '22/10/2026', 'hasta': '21/10/2026'}).status_code == 400


@pytest.mark.parametrize('start,end,expected', [
    ('01/11/2026', '15/11/2026', 15), ('01/11/2026', '01/11/2026', 1),
    ('28/02/2028', '01/03/2028', 3), ('07/11/2026', '08/11/2026', 2),
    ('31/12/2026', '01/01/2027', 2),
])
def test_vacation_calendar_days_ignore_tampered_total(app, admin, start, end, expected):
    data = form_values(admin, VAC, {**VAC_DATA, 'fecha_inicio': start, 'fecha_termino': end,
                                   'total_dias': '999999', 'usuario_registro_id': '999999'})
    response = admin.post(VAC, data=data, follow_redirects=True)
    assert response.status_code == 200 and 'Vacaciones registradas correctamente' in response.text
    assert 'value="Ana Ejemplo"' not in response.text
    with app.app_context():
        row = db.session.scalar(db.select(Vacacion))
        assert row.total_dias == expected and row.usuario_registro.username == 'victor'


@pytest.mark.parametrize('change', [
    {'nombres_apellidos': ''}, {'fecha_inicio': ''}, {'fecha_termino': ''},
    {'fecha_termino': '31/10/2026'}, {'fecha_inicio': '31/02/2026'},
    {'funcionario_id': ''},
])
def test_vacation_invalid_fields_and_reverse_range(app, admin, change):
    data = form_values(admin, VAC, VAC_DATA)
    assert admin.post(VAC, data={**data, **change}).status_code == 422
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Vacacion)) == 0


def test_vacation_edit_recalculates_and_prevents_stale_write(app, admin):
    admin.post(VAC, data=form_values(admin, VAC, VAC_DATA))
    with app.app_context():
        row = db.session.scalar(db.select(Vacacion))
        rid, created, owner = row.id, row.fecha_creacion, row.usuario_registro_id
    url = f'{VAC}{rid}/editar'
    page = admin.get(url)
    assert 'readonly' in page.text and 'value="15"' in page.text
    data = form_values(admin, url, {**VAC_DATA, 'fecha_termino': '20/11/2026', 'total_dias': 'no-es-un-numero'})
    assert admin.post(url, data=data).status_code == 303
    assert admin.post(url, data={**data, 'fecha_termino': '21/11/2026'}).status_code == 409
    with app.app_context():
        row = db.session.get(Vacacion, rid)
        assert row.total_dias == 20 and row.fecha_termino == date(2026, 11, 20)
        assert row.fecha_creacion == created and row.usuario_registro_id == owner
        assert row.usuario_modificacion_id == owner and row.version == 2


def test_vacation_overlap_filters_and_chronological_order(admin):
    admin.post(VAC, data=form_values(admin, VAC, VAC_DATA))
    with admin.application.app_context():
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'victor'))
        employee = create_employee({
            'nombres': 'Carlos', 'apellidos': 'Ejemplo', 'cedula': '88776655',
            'carrera': 'TEC. EN ENFERMERIA', 'fecha_nacimiento': date(1990, 5, 15),
            'fecha_ingreso': date(2016, 3, 10), 'direccion_actual': 'Domicilio de prueba',
            'servicio_id': 1,
        }, [], str(uuid4()), user.id)
        db.session.commit()
        second_employee_id = employee.id
    second = {**VAC_DATA, 'nombres_apellidos': 'Carlos Ejemplo', 'fecha_inicio': '01/12/2026',
        'fecha_termino': '05/12/2026', 'funcionario_id': str(second_employee_id)}
    admin.post(VAC, data=form_values(admin, VAC, second))
    filtered = admin.get(VAC, query_string={'desde': '10/11/2026', 'hasta': '10/11/2026'})
    assert 'Ana Ejemplo' in filtered.text and 'Carlos Ejemplo' not in filtered.text
    page = admin.get(VAC).text
    assert page.index('Ana Ejemplo') < page.index('Carlos Ejemplo')
    assert 'Ana Ejemplo' not in admin.get(VAC, query_string={'q': 'carlos'}).text
    assert admin.get(VAC, query_string={'orden': 'invalido'}).status_code == 400


@pytest.mark.parametrize(('career', 'rubro'), [
    ('LIC. EN ENFERMERIA', '111'),
    ('TEC. EN ENFERMERIA', '142'),
    ('AUX. EN ENFERMERA', ''),
    ('CAMILLERO', ''),
])
def test_vacation_print_and_excel_use_the_roster_template(app, admin, career, rubro):
    admin.post(VAC, data=form_values(admin, VAC, VAC_DATA))
    with app.app_context():
        employee = db.session.scalar(db.select(Funcionario).where(Funcionario.cedula == '99887766'))
        employee.carrera = career
        if not any(link.activo and link.numero_vinculo == 2 for link in employee.vinculos):
            user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'victor'))
            add_link(employee.id, date(2018, 4, 1), user.id, str(uuid4()))
        db.session.commit()

    params = {'desde': '01/11/2026', 'hasta': '30/11/2026'}
    page = admin.get(VAC + 'planilla', query_string=params)
    assert page.status_code == 200
    for value in ('PLANILLA TENTATIVA DE PERIODO VACACIONAL 2026/2027',
                  'NOMBRES Y APELLIDOS', 'C.I. Nº', 'RUBRO', 'FUNCION',
                  '01/11/2026', '15/11/2026', '99887766', career, 'vacation_roster_logo.jpeg'):
        assert value in page.text
    assert f'<td>{rubro}</td>' in page.text
    assert '<td>1</td>' in page.text
    assert '<td></td></tr>' in page.text

    response = admin.get(VAC + 'planilla.xlsx', query_string=params)
    assert response.status_code == 200
    assert response.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    assert response.headers['Cache-Control'] == 'no-store'
    with zipfile.ZipFile(BytesIO(response.data)) as workbook:
        sheet = ET.fromstring(workbook.read('xl/worksheets/sheet1.xml'))
        ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        cells = {cell.get('r'): cell for cell in sheet.findall('.//m:sheetData/m:row/m:c', ns)}

        def value(cell_ref):
            cell = cells[cell_ref]
            text = cell.find('m:is/m:t', ns)
            node = cell.find('m:v', ns)
            return text.text if text is not None else node.text if node is not None else ''

        assert value('C7') == 'C.I. Nº'
        assert value('G7') == 'ANTIGÜEDAD'
        assert [value(f'{column}9') for column in ('A', 'B', 'C', 'D', 'E', 'G', 'K')] == [
            '1', 'Ana Ejemplo', '99887766', rubro, career, '11 años, 7 meses, 22 días', '1, 2']
        assert value('J9') == '15'
        assert value('F9') == str((date(2015, 3, 10) - date(1899, 12, 30)).days)
        assert value('H9') == str((date(2026, 11, 1) - date(1899, 12, 30)).days)
        assert value('I9') == str((date(2026, 11, 15) - date(1899, 12, 30)).days)
        assert value('L9') == ''
        assert sheet.find('m:mergeCells/m:mergeCell[@ref="A1:L1"]', ns) is not None
        assert sheet.find('m:pageSetup', ns).get('orientation') == 'portrait'


@pytest.mark.parametrize('path,model,values', [(COM, Comisionado, COM_DATA), (VAC, Vacacion, VAC_DATA)])
def test_leave_double_submit_and_legitimate_new_record(app, admin, path, model, values):
    data = form_values(admin, path, values)
    assert admin.post(path, data=data).status_code == 303
    assert admin.post(path, data=data).status_code == 303
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(model)) == 1
    assert admin.post(path, data=form_values(admin, path, values)).status_code == 303
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(model)) == 2


def test_leave_records_persist_after_logout_and_new_app(app, admin):
    data = form_values(admin, COM, COM_DATA)
    admin.post(COM, data=data)
    admin.post(VAC, data=form_values(admin, VAC, VAC_DATA))
    assert admin.post('/logout', data={'csrf_token': data['csrf_token']}).status_code == 302
    assert admin.get(COM).status_code == 302
    assert login(admin).status_code == 302
    assert 'Ana Ejemplo' in admin.get(COM).text and 'Ana Ejemplo' in admin.get(VAC).text
    fresh = create_app({'TESTING': True, 'SECRET_KEY': app.secret_key,
        'SQLALCHEMY_DATABASE_URI': app.config['SQLALCHEMY_DATABASE_URI'], 'SESSION_COOKIE_SECURE': False})
    with fresh.app_context():
        assert db.session.scalar(db.select(Comisionado)).lugar == 'Ciudad del Este'
        assert db.session.scalar(db.select(Vacacion)).total_dias == 15


def test_new_modules_role_and_no_delete_routes(app, client):
    with app.app_context():
        operator = db.session.scalar(db.select(Usuario).where(Usuario.username == 'operador_test'))
        if not operator:
            operator = Usuario(nombre='Operador', username='operador_test', rol='OPERADOR', activo=True, debe_cambiar_password=False)
            db.session.add(operator)
        operator.set_password('clave-operador-test')
        db.session.commit()
    login(client, 'operador_test', 'clave-operador-test')
    for path in (COM, VAC):
        assert client.get(path).status_code == 200
        assert 'id="registros"' not in client.get(path).text
    for path in (COM + '1/editar', VAC + '1/editar'):
        assert client.get(path).status_code == 403


def test_new_record_save_error_preserves_fields(admin):
    data = form_values(admin, VAC, VAC_DATA)
    with patch('app.administration.leave_records.create_record', side_effect=SQLAlchemyError()):
        response = admin.post(VAC, data=data)
    assert response.status_code == 503
    assert 'value="Ana Ejemplo"' in response.text and 'value="15"' in response.text


def test_postgresql_rejects_inconsistent_vacation_total(app):
    with app.app_context():
        user_id = db.session.scalar(db.select(Usuario.id).where(Usuario.username == 'victor'))
        for start, end, total in [(date(2026, 11, 1), date(2026, 11, 15), 999),
                                  (date(2026, 11, 15), date(2026, 11, 1), -13)]:
            row = Vacacion(nombres_apellidos='Prueba Restricción', fecha_inicio=start,
                servicio_id=1,
                fecha_termino=end, total_dias=total, usuario_registro_id=user_id, solicitud_id=uuid4())
            db.session.add(row)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()
