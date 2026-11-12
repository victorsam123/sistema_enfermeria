import re
from io import BytesIO
from datetime import date
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import pytest
from flask_migrate import upgrade
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, DBAPIError
from app import create_app
from app.extensions import db
from app.models import Usuario
from app.models.administration import Justificativo, CambioGuardia, DetalleCambioGuardia
from app.models.reposos import Reposo
from app.models.leave_records import Vacacion, Comisionado
from app.models.hospital_services import Servicio, HistorialAdministrativo
from app.hospital_services.catalog import INITIAL_SERVICES, SHEET_NAMES
from app.hospital_services.classification import can_view_diagnosis
from app.hospital_services.excel import worksheet_name
from app.services import initialize_admin
from test_auth import login
from test_administration import JUST_DATA, GUARD_DATA, form_values
from test_reposos import DATA as REST_DATA
from test_leave_records import VAC_DATA, COM_DATA
from test_guardias_multifecha import form_data, NAMES, DETAILS
from test_record_helpers import associate_employee

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
NORMAL = '/reposo/cambio-guardia/'
PAID = '/reposo/cambio-guardia-pagada/'


@pytest.fixture(autouse=True)
def clean_service_records(app):
    with app.app_context():
        for model in (HistorialAdministrativo, DetalleCambioGuardia, CambioGuardia, Justificativo, Reposo, Vacacion, Comisionado):
            db.session.execute(db.delete(model))
        for code, name in INITIAL_SERVICES:
            s = db.session.scalar(db.select(Servicio).where(Servicio.codigo == code))
            s.nombre, s.activo = name, True
        db.session.commit()
    yield
    with app.app_context():
        db.session.rollback()
        for model in (HistorialAdministrativo, DetalleCambioGuardia, CambioGuardia, Justificativo, Reposo, Vacacion, Comisionado):
            db.session.execute(db.delete(model))
        for code, name in INITIAL_SERVICES:
            s = db.session.scalar(db.select(Servicio).where(Servicio.codigo == code))
            s.nombre, s.activo = name, True
        db.session.commit()


@pytest.fixture
def admin(client):
    assert login(client).status_code == 302
    return client


def token(client, url):
    page = client.get(url)
    assert page.status_code == 200
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text).group(1)


def report(client, service=1, category='completo', start='01/10/2026', end='30/10/2026', action='descargar'):
    return client.post('/informes/', data={'csrf_token': token(client, '/informes/'),
        'servicio_id': str(service), 'categoria': category, 'desde': start, 'hasta': end, 'accion': action})


def workbook(response):
    assert response.status_code == 200, response.text[:1000] if response.is_json else response.status_code
    z = ZipFile(BytesIO(response.data))
    assert z.testzip() is None
    root = ET.fromstring(z.read('xl/workbook.xml'))
    sheets = [s.attrib['name'] for s in root.find('s:sheets', NS)]
    strings = ET.fromstring(z.read('xl/sharedStrings.xml'))
    shared = [''.join(si.itertext()) for si in strings]
    data = {}
    for index, name in enumerate(sheets, 1):
        xml = ET.fromstring(z.read(f'xl/worksheets/sheet{index}.xml'))
        cells = {}
        for c in xml.findall('.//s:sheetData/s:row/s:c', NS):
            v = c.findtext('s:v', None, NS)
            cells[c.attrib['r']] = shared[int(v)] if v is not None and c.attrib.get('t') == 's' else v
        data[name] = {'xml': xml, 'cells': cells}
    return z, sheets, data


def test_catalog_is_idempotent_and_dashboard_integrates_access(app, admin):
    with app.app_context():
        before = [(s.id, s.codigo, s.nombre) for s in db.session.scalars(db.select(Servicio).order_by(Servicio.id))]
        upgrade()
        after = [(s.id, s.codigo, s.nombre) for s in db.session.scalars(db.select(Servicio).order_by(Servicio.id))]
        assert before == after
        assert {c for _, c, _ in after}.issuperset(dict(INITIAL_SERVICES))
        assert 'Hoja1' not in {name for _, _, name in after}
    page = admin.get('/').text
    assert 'href="/archivos-por-servicio/"' in page and 'href="/informes/"' in page


@pytest.mark.parametrize('path,values', [('/justificativos/', JUST_DATA), ('/reposo/', REST_DATA),
    (NORMAL, GUARD_DATA), (PAID, GUARD_DATA), ('/vacaciones/', VAC_DATA), ('/comisionados/', COM_DATA)])
def test_all_new_records_require_real_active_service(app, admin, path, values):
    for invalid in ('', '0', '999999', '15'):
        data = form_values(admin, path, {**values, 'servicio_id': invalid})
        response = admin.post(path, data=data)
        assert response.status_code == 422
    data = form_values(admin, path, values)
    del data['servicio_id']
    assert admin.post(path, data=data).status_code == 422
    with app.app_context():
        assert all(db.session.scalar(db.select(db.func.count()).select_from(m)) == 0
            for m in (Justificativo, Reposo, CambioGuardia, Vacacion, Comisionado))
    data = form_values(admin, path, {**values, 'servicio_id': '1'})
    if path == '/vacaciones/':
        data = associate_employee(app, data, Vacacion, 'vacaciones')
    elif path == PAID:
        data = associate_employee(app, data, CambioGuardia, 'pagadas')
    saved = admin.post(path, data=data, follow_redirects=True)
    assert saved.status_code == 200
    assert 'Registro guardado correctamente en el servicio UTI - P' in saved.text


def test_virtual_folders_are_unique_and_isolate_categories_and_services(app, admin):
    for n in range(2):
        admin.post('/justificativos/', data=form_values(admin, '/justificativos/',
            {**JUST_DATA, 'nombres_apellidos': f'Justificativo UTI Persona {n}', 'servicio_id': '1'}))
    admin.post('/reposo/', data=form_values(admin, '/reposo/', {**REST_DATA, 'servicio_id': '7'}))
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Servicio).where(Servicio.codigo == 'UTI-P')) == 1
    index = admin.get('/archivos-por-servicio/').text
    assert index.count('href="/archivos-por-servicio/1/"') == 1
    assert '2</strong> registros' in index
    assert 'Justificativo UTI Persona' in admin.get('/archivos-por-servicio/1/justificativos/').text
    assert 'Funcionario Ejemplo' not in admin.get('/archivos-por-servicio/1/reposos/').text
    assert 'Funcionario Ejemplo' in admin.get('/archivos-por-servicio/7/reposos/').text
    assert admin.get('/archivos-por-servicio/1/').status_code == 200


def test_reclassification_and_normal_edit_audit_old_new_and_stale(app, admin):
    admin.post('/justificativos/', data=form_values(admin, '/justificativos/', JUST_DATA))
    with app.app_context():
        item = db.session.scalar(db.select(Justificativo))
        rid, version, creator, created = item.id, str(item.version), item.usuario_registro_id, item.fecha_creacion
    path = f'/archivos-por-servicio/reclasificar/justificativos/{rid}'
    data = {'csrf_token': token(admin, path), 'version': version, 'servicio_id': '7'}
    assert admin.post(path, data=data).status_code == 303
    assert admin.post(path, data=data).status_code == 409
    edit = f'/justificativos/{rid}/editar'
    assert admin.post(edit, data=form_values(admin, edit, {**JUST_DATA, 'servicio_id': '1'})).status_code == 303
    with app.app_context():
        history = db.session.scalars(db.select(HistorialAdministrativo).where(HistorialAdministrativo.evento == 'RECLASIFICACION').order_by(HistorialAdministrativo.id)).all()
        assert [(e.servicio_anterior_id, e.servicio_nuevo_id) for e in history] == [(1, 7), (7, 1)]
        item = db.session.get(Justificativo, rid)
        assert (item.usuario_registro_id, item.fecha_creacion) == (creator, created)
        assert item.usuario_modificacion_id == creator
    assert 'RECLASIFICACION' in admin.get('/configuracion/servicios/historial').text


def test_guardia_service_and_dates_move_as_single_operation(app, admin):
    admin.post(NORMAL, data=form_data(admin, NORMAL))
    with app.app_context():
        item = db.session.scalar(db.select(CambioGuardia))
        rid = item.id
        details = [dict(detalle_id=str(d.id), participante=d.participante, fecha_guardia=d.fecha_guardia.strftime('%d/%m/%Y'),
            hora_inicio=d.hora_inicio.strftime('%H:%M'), hora_fin=d.hora_fin.strftime('%H:%M'), codigo=d.codigo) for d in item.detalles]
    path = f'{NORMAL}{rid}/editar'
    values = form_data(admin, path, details=details)
    values['servicio_id'] = '7'
    assert admin.post(path, data=values).status_code == 303
    assert 'Gloria Ejemplo' not in admin.get('/archivos-por-servicio/1/guardias/').text
    assert 'Gloria Ejemplo' in admin.get('/archivos-por-servicio/7/guardias/').text
    with app.app_context():
        assert len(db.session.get(CambioGuardia, rid).detalles) == 2
        assert db.session.scalar(db.select(HistorialAdministrativo).where(HistorialAdministrativo.evento == 'RECLASIFICACION')).evento == 'RECLASIFICACION'


def test_export_real_dates_overlap_independent_guardias_and_service_isolation(app, admin):
    for name, when, service in [('Incluido octubre', '01/10/2026', '1'), ('Fuera septiembre', '30/09/2026', '1'),
                                ('Otro servicio', '02/10/2026', '7'), ('Final incluido', '30/10/2026', '1')]:
        admin.post('/justificativos/', data=form_values(admin, '/justificativos/',
            {**JUST_DATA, 'nombres_apellidos': name, 'fecha_inasistencia': when, 'fecha_cobertura': '', 'servicio_id': service}))
    admin.post('/reposo/', data=form_values(admin, '/reposo/', {**REST_DATA, 'fecha_desde': '28/09/2026',
        'fecha_hasta': '05/10/2026', 'diagnostico': 'Diagnóstico de prueba solapado'}))
    vacation = form_values(admin, '/vacaciones/', {**VAC_DATA,
        'fecha_inicio': '29/09/2026', 'fecha_termino': '02/10/2026'})
    vacation = associate_employee(app, vacation, Vacacion, 'vacaciones')
    admin.post('/vacaciones/', data=vacation)
    admin.post('/comisionados/', data=form_values(admin, '/comisionados/', COM_DATA))
    details = [dict(DETAILS[0], fecha_guardia='30/09/2026'), dict(DETAILS[1], fecha_guardia='02/10/2026'),
        dict(DETAILS[0], fecha_guardia='08/10/2026'), dict(DETAILS[1], fecha_guardia='17/10/2026'),
        dict(DETAILS[0], fecha_guardia='01/11/2026')]
    assert admin.post(NORMAL, data=form_data(admin, NORMAL, details=details)).status_code == 303
    paid = form_data(admin, PAID, names={'solicitante': 'Pagado Solicitante', 'reemplazante': 'Pagado Reemplazante'})
    paid = associate_employee(app, paid, CambioGuardia, 'pagadas')
    assert admin.post(PAID, data=paid).status_code == 303
    response = report(admin)
    z, sheets, data = workbook(response)
    all_values = [v for s in data.values() for v in s['cells'].values()]
    assert 'Incluido octubre' in all_values and 'Final incluido' in all_values
    assert 'Fuera septiembre' not in all_values and 'Otro servicio' not in all_values
    assert 'SIN COBERTURA' in all_values and 'Diagnóstico de prueba solapado' in all_values
    assert data['UTI-P']['cells']['A6'] == 'CAMBIO DE GUARDIA'
    assert data['UTI-P']['cells']['G6'] == 'JUSTIFICATIVO'
    assert data['UTI-P']['cells']['K6'] == 'REPOSO'
    assert any(n.endswith('_VACACIONES') for n in sheets) and any(n.endswith('_COMISIONADOS') for n in sheets)
    g = next(s for n, s in data.items() if n.endswith('_GUARDIAS'))
    # Cabecera fila 7, exactamente tres detalles de guardia dentro de octubre.
    assert len([c for c in g['cells'] if re.fullmatch(r'G(?:[89]|10)', c)]) == 3
    assert 'G11' not in g['cells']
    assert [g['cells'][f'F{r}'] for r in (8, 9, 10)] == ['R', 'S', 'R']
    assert [g['cells'][f'K{r}'] for r in (8, 9, 10)] == ['L', 'G', 'L']
    assert g['cells']['G8'] == str((date(2026, 10, 2) - date(1899, 12, 30)).days)
    assert g['cells']['J9'] == str((date(2026, 10, 9) - date(1899, 12, 30)).days)
    assert '<f>' not in z.read('xl/worksheets/sheet1.xml').decode()
    assert b'dd/mm/yyyy' in z.read('xl/styles.xml') and b'hh:mm' in z.read('xl/styles.xml')
    rest = next(s for n, s in data.items() if n.endswith('_REPOSOS'))
    assert rest['cells']['D8'] == '8'  # Total original completo, no recortado al rango.
    vac = next(s for n, s in data.items() if n.endswith('_VACACIONES'))
    assert vac['cells']['D8'] == '4'
    assert 'attachment' in response.headers['Content-Disposition']
    assert 'no-store' in response.headers['Cache-Control']
    for sheet in data.values():
        setup = sheet['xml'].find('s:pageSetup', NS)
        assert setup.attrib['orientation'] == 'landscape' and setup.attrib['paperSize'] == '9'
        assert setup.attrib.get('fitToWidth', '1') == '1'  # 1 es el valor predeterminado OOXML.
        assert sheet['xml'].find('s:sheetPr/s:pageSetUpPr', NS).attrib['fitToPage'] == '1'
    assert b'_xlnm.Print_Area' in z.read('xl/workbook.xml') and b'_xlnm.Print_Titles' in z.read('xl/workbook.xml')
    with app.app_context():
        events = db.session.scalars(db.select(HistorialAdministrativo).where(HistorialAdministrativo.entidad == 'informes')).all()
        assert {e.evento for e in events} == {'INFORME_GENERADO', 'INFORME_DESCARGADO'}
        assert all(e.usuario.username == 'victor' and e.detalles['desde'] == '2026-10-01' for e in events)
    # Solo muestra ficticia de la base _test, nunca datos de la aplicación.
    destination = Path('.runtime/qa_actualizacion7_final.xlsx')
    destination.write_bytes(response.data)


def test_all_services_empty_export_names_unique_and_original_headers(app, admin):
    response = report(admin, service=0, start='01/01/1901', end='01/01/1901')
    z, sheets, data = workbook(response)
    expected = {SHEET_NAMES.get(code, code) for code, _ in INITIAL_SERVICES}
    assert set(sheets).issuperset(expected)
    assert 'Hoja1' not in sheets and len({n.casefold() for n in sheets}) == len(sheets)
    assert all(len(n) <= 31 for n in sheets)
    for name in expected:
        assert 'Sin registros en el período seleccionado' in data[name]['cells'].values()
    assert not any('qa_actualizacion7' in n for n in z.namelist())


def test_all_services_export_does_not_mix_records(admin):
    admin.post('/justificativos/', data=form_values(admin, '/justificativos/',
        {**JUST_DATA, 'nombres_apellidos': 'Dato exclusivo UTI', 'servicio_id': '1'}))
    admin.post('/reposo/', data=form_values(admin, '/reposo/',
        {**REST_DATA, 'nombres_apellidos': 'Dato exclusivo Trauma', 'servicio_id': '7'}))
    _, _, data = workbook(report(admin, service=0))
    assert 'Dato exclusivo UTI' in data['UTI-P']['cells'].values()
    assert 'Dato exclusivo Trauma' not in data['UTI-P']['cells'].values()
    assert 'Dato exclusivo Trauma' in data['URGE-TRAUMA']['cells'].values()
    assert 'Dato exclusivo UTI' not in data['URGE-TRAUMA']['cells'].values()


@pytest.mark.parametrize('kind', ['justificativos', 'reposos', 'guardias', 'pagadas', 'vacaciones', 'comisionados'])
def test_selected_category_preview_generate_and_download_agree(admin, kind):
    for action in ('previa', 'generar', 'descargar'):
        result = report(admin, category=kind, action=action)
        assert result.status_code == 200
        if action == 'descargar':
            _, sheets, data = workbook(result)
            assert len(sheets) == 2
        else:
            assert 'Vista previa del informe' in result.text and 'Sin registros en el período seleccionado' in result.text


def test_export_literal_strings_not_excel_formulas(admin):
    values = {**JUST_DATA, 'nombres_apellidos': '=1+1', 'motivo': '=HYPERLINK("https://example.invalid","texto")'}
    assert admin.post('/justificativos/', data=form_values(admin, '/justificativos/', values)).status_code == 303
    z, _, _ = workbook(report(admin, category='justificativos'))
    for name in z.namelist():
        if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
            assert b'<f>' not in z.read(name) and b'<hyperlink ' not in z.read(name)


def test_reports_filters_errors_and_size_limit(app, admin):
    assert report(admin, start='31/02/2026').status_code == 422
    assert report(admin, end='30/09/2026').status_code == 422
    assert report(admin, service=999999).status_code == 422
    assert report(admin, category='intruso').status_code == 422
    assert report(admin, action='intruso').status_code == 400
    assert admin.post('/informes/', data={}).status_code == 400
    assert admin.get('/informes/?accion=descargar').mimetype == 'text/html'
    admin.post('/justificativos/', data=form_values(admin, '/justificativos/', JUST_DATA))
    app.config['MAX_REPORT_ROWS'] = 0
    try:
        assert report(admin).status_code == 413
    finally:
        app.config.pop('MAX_REPORT_ROWS')


@pytest.mark.parametrize('path', ['/archivos-por-servicio/', '/archivos-por-servicio/1/',
    '/archivos-por-servicio/1/reposos/', '/informes/', '/configuracion/servicios/', '/configuracion/servicios/historial'])
def test_private_routes_and_diagnoses_require_authorization(app, client, path):
    assert client.get(path).status_code == 302
    with app.app_context():
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'report_operator'))
        if not user:
            user = Usuario(username='report_operator', nombre='Operador', rol='OPERADOR', activo=True, debe_cambiar_password=False)
            db.session.add(user)
        user.set_password('operator-test-only')
        db.session.commit()
    assert login(client, 'report_operator', 'operator-test-only').status_code == 302
    assert client.get(path).status_code == 403
    with app.test_request_context():
        assert not can_view_diagnosis()


def test_postgresql_requires_active_real_service_and_prevents_catalog_deletion(app):
    with app.app_context():
        uid = db.session.scalar(db.select(Usuario.id).where(Usuario.username == 'victor'))
        for service_id in (None, 0, 999999, 15):
            db.session.add(Justificativo(nombres_apellidos='Prueba SQL Servicio', fecha_inasistencia=date(2026, 10, 1),
                motivo='Prueba de integridad', servicio_id=service_id, usuario_registro_id=uid, solicitud_id=uuid4()))
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()
        for statement in ("DELETE FROM servicios WHERE codigo='UTI-P'", 'TRUNCATE servicios CASCADE',
                          "UPDATE servicios SET codigo='OTRO' WHERE codigo='UTI-P'",
                          "UPDATE servicios SET activo=true WHERE codigo='PENDIENTE'"):
            with pytest.raises(DBAPIError):
                db.session.execute(db.text(statement))
                db.session.commit()
            db.session.rollback()


def test_service_configuration_preserves_foreign_keys_and_deactivated_records(app, admin):
    admin.post('/justificativos/', data=form_values(admin, '/justificativos/', JUST_DATA))
    path = '/configuracion/servicios/1/editar'
    page = admin.get(path)
    version = re.search(r'name="version"[^>]*value="([^"]+)"', page.text).group(1)
    assert admin.post(path, data={'csrf_token': token(admin, path), 'version': version,
        'codigo': 'UTI-P', 'nombre': 'UTI Pediátrica'}).status_code == 303
    assert 'UTI Pediátrica' in admin.get('/archivos-por-servicio/1/justificativos/').text
    assert 'value="1"' not in re.search(r'<select[^>]*id="servicio_id".*?</select>', admin.get('/justificativos/').text, re.S).group(0)
    assert report(admin).status_code == 200  # Los datos históricos siguen consultables.
    assert admin.post('/justificativos/', data=form_values(admin, '/justificativos/', JUST_DATA)).status_code == 422
    assert admin.get('/configuracion/servicios/15/editar').status_code == 403


def test_add_service_rejects_duplicate_code_and_persists_after_new_app(app, admin):
    path = '/configuracion/servicios/'
    code = 'TEST-EXTRA'
    with app.app_context():
        exists = db.session.scalar(db.select(Servicio.id).where(Servicio.codigo == code))
    result = admin.post(path, data={'csrf_token': token(admin, path), 'nombre': 'Servicio de prueba', 'codigo': code, 'activo': 'y'})
    assert result.status_code == (409 if exists else 303)
    assert admin.post(path, data={'csrf_token': token(admin, path), 'nombre': 'Duplicado', 'codigo': code, 'activo': 'y'}).status_code == 409
    retry = admin.post(path, data={'csrf_token': token(admin, path), 'nombre': 'Duplicado', 'codigo': code, 'activo': 'y'})
    assert 'readonly' not in re.search(r'<input[^>]*id="codigo"[^>]*>', retry.text).group(0)
    fresh = create_app({'TESTING': True, 'SECRET_KEY': app.secret_key, 'SQLALCHEMY_DATABASE_URI': app.config['SQLALCHEMY_DATABASE_URI'], 'SESSION_COOKIE_SECURE': False})
    with fresh.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Servicio).where(Servicio.codigo == code)) == 1


def test_migration7_keeps_every_legacy_column_and_pending_classification(app):
    schema = 'migracion7_' + uuid4().hex
    with app.app_context():
        assert make_url(app.config['SQLALCHEMY_DATABASE_URI']).database.endswith('_test')
        db.session.execute(db.text('CREATE SCHEMA ' + schema))
        db.session.commit()
    isolated = create_app({'TESTING': True, 'SECRET_KEY': app.secret_key,
        'SQLALCHEMY_DATABASE_URI': app.config['SQLALCHEMY_DATABASE_URI'], 'SESSION_COOKIE_SECURE': False,
        'SQLALCHEMY_ENGINE_OPTIONS': {'connect_args': {'options': '-csearch_path=' + schema}}})
    with isolated.app_context():
        upgrade(revision='0005_guardias_fechas_y_cobertura')
        from legacy_migration_helpers import legacy_admin
        uid = legacy_admin()
        db.session.execute(db.text("""INSERT INTO justificativos(nombres_apellidos,fecha_inasistencia,motivo,usuario_registro_id,solicitud_id)
            VALUES ('Dato antiguo','2026-10-01','Motivo conservado',:uid,:uuid)"""), {'uid': uid, 'uuid': uuid4()})
        db.session.commit()
        previous = db.session.execute(db.text('SELECT * FROM justificativos')).one()
        user = db.session.execute(db.text("SELECT id,username,password_hash,rol,activo,protegido FROM usuarios WHERE username='victor'")).one()
        db.session.remove()
        upgrade()
        after = db.session.execute(db.text('SELECT * FROM justificativos')).one()
        assert after[:len(previous)] == previous
        item = db.session.scalar(db.select(Justificativo))
        assert item.servicio.codigo == 'PENDIENTE' and item.fecha_cobertura is None
        actual_user = db.session.execute(db.text("SELECT id,username,password_hash,rol,activo,protegido FROM usuarios WHERE username='victor'")).one()
        assert actual_user[:3] == user[:3] and actual_user[4:] == user[4:] and actual_user.rol == 'SUPERADMIN'
        assert db.session.scalar(db.select(db.func.count()).select_from(Servicio)) == 15


def test_sheet_names_respect_excel_limits_and_reservations():
    used = set()
    first = worksheet_name('A' * 50, used)
    second = worksheet_name('A' * 50, used)
    history = worksheet_name('HISTORY', used)
    bad = worksheet_name("'SERVICIO/A:B[?]*'", used)
    assert first != second and len(first) <= 31 and len(second) <= 31
    assert history.casefold() != 'history'
    assert not re.search(r"[\[\]:*?/\\']", bad)
