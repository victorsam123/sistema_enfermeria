"""Regresi?n de documentos oficiales sobre PostgreSQL de pruebas."""
from datetime import date
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import ZipFile
import re
import xml.etree.ElementTree as ET
from unittest.mock import patch
import subprocess
import pytest
from sqlalchemy.exc import SQLAlchemyError
from app.extensions import db
from app.models import Usuario
from app.models.administration import Justificativo
from app.models.issued_notes import NotaCompensatoria
from app.employees.services import create_employee
from app.administration.compensatory_document import render_compensatory_note, excluded_reason
from app.administration.office_documents import OfficeConversionError, convert_to_pdf
from test_auth import login

URL = '/justificativos/notas-compensatorias/'

@pytest.fixture
def prepared(app, client):
    assert login(client).status_code == 302
    with app.app_context():
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == 'victor'))
        person = create_employee(dict(nombres='Documento', apellidos='Prueba', cedula=str(uuid4().int)[:12],
            carrera='LIC. EN ENFERMERIA', fecha_nacimiento=date(1990,1,1), fecha_ingreso=date(2015,1,1),
            direccion_actual='Direcci?n de prueba', servicio_id=1), [], str(uuid4()), user.id)
        record = Justificativo(nombres_apellidos=person.nombre_completo, funcionario_id=person.id,
            servicio_id=1, fecha_inasistencia=date(2026,11,2), fecha_cobertura=date(2026,11,1),
            motivo='D?a compensatorio por servicios extraordinarios', usuario_registro_id=user.id, solicitud_id=uuid4())
        db.session.add(record)
        db.session.commit()
        rid, pid, version = record.id, person.id, record.version
    page = client.get(URL)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text).group(1)
    selection = client.post(URL, data=dict(csrf_token=token, accion='preparar', registros=str(rid), confirmar='y'))
    assert selection.status_code == 200
    request_id = re.search(r'name="solicitud_id"[^>]*value="([^"]+)"', selection.text).group(1)
    data = dict(csrf_token=token, solicitud_id=request_id, numero=str(uuid4().int % 900000 + 1),
        fecha_emision='02/11/2026', confirmar='y', accion='emitir')
    data.update({'filas-0-justificativo_id': str(rid), 'filas-0-version': str(version),
        'filas-0-funcionario_id': str(pid), 'filas-0-fecha_realizacion': '01/11/2026',
        'filas-0-fecha_libre': '02/11/2026', 'filas-0-horario_cumplido': '18:00 a 06:00',
        'filas-0-horario_libre': '06:00 a 12:00'})
    return data, rid

def test_notes_require_session_and_csrf(client):
    assert client.get(URL).status_code == 302
    assert login(client).status_code == 302
    assert client.post(URL, data={}).status_code == 400

@pytest.mark.parametrize('reason', ['Capacitaci?n', 'Llegada tard?a', 'Falta de marcaci?n de entrada', 'Sin marcaci?n'])
def test_excluded_reasons(reason):
    assert excluded_reason(reason)

@pytest.mark.parametrize('count', [1, 16, 40])
def test_word_preserves_template_and_expands_rows(app, count):
    rows = [dict(name='Persona de prueba', cedula='9000001', worked_dates='01/11/2026',
        free_dates='02/11/2026', worked_hours='18:00 a 06:00', free_hours='06:00 a 12:00', service='PAI')] * count
    with app.app_context():
        content = render_compensatory_note(rows, 55, date(2026,11,2))
    with ZipFile(BytesIO(content)) as final, ZipFile(Path(app.root_path)/'assets/nota_dia_compensatorio.docx') as source:
        assert final.namelist() == source.namelist()
        assert all(final.read(p) == source.read(p) for p in source.namelist() if p != 'word/document.xml')
        root = ET.fromstring(final.read('word/document.xml'))
        assert len(root.findall('.//w:tbl/w:tr', {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'})) == count + 1
        assert 'NOTA N.ª  55' in ''.join(root.itertext())

def test_word_download_does_not_issue(app, client, prepared):
    data, rid = prepared
    response = client.post(URL, data={**data, 'accion':'word'})
    assert response.status_code == 200 and response.data.startswith(b'PK')
    assert 'no-store' in response.headers['Cache-Control']
    with app.app_context():
        assert db.session.scalar(db.select(NotaCompensatoria.id).where(NotaCompensatoria.solicitud_id == UUID(data['solicitud_id']))) is None
        assert db.session.get(Justificativo, rid).version == 1

def test_issue_is_idempotent_and_downloads_are_private(app, client, prepared):
    data, rid = prepared
    with patch('app.administration.compensatory_notes.convert_to_pdf', return_value=b'%PDF-1.4 test'):
        response = client.post(URL, data=data)
        assert response.status_code == 303, response.text
        again = client.post(URL, data=data)
        assert again.status_code == 303 and again.location == response.location
        duplicate = client.post(URL, data={**data, 'solicitud_id':str(uuid4())})
        assert duplicate.status_code == 422
    for suffix in ('word', 'pdf', 'vista'):
        downloaded = client.get(response.location + '/' + suffix)
        assert downloaded.status_code == 200
        assert 'no-store' in downloaded.headers['Cache-Control']
    with app.app_context():
        assert db.session.get(Justificativo, rid).version == 1
        note = db.session.scalar(db.select(NotaCompensatoria).where(NotaCompensatoria.numero == int(data['numero'])))
        with pytest.raises(SQLAlchemyError):
            db.session.execute(db.text('UPDATE notas_compensatorias SET numero=numero+1 WHERE id=:id'), {'id':note.id})
            db.session.commit()
        db.session.rollback()

@pytest.mark.parametrize('change', [{'filas-0-version':'999'}, {'filas-0-fecha_libre':'03/11/2026'},
    {'filas-0-horario_cumplido':'29:00 a 06:00'}, {'confirmar':''}])
def test_note_rejects_stale_or_invalid_data(client, prepared, change):
    data, _ = prepared
    assert client.post(URL, data={**data, **change}).status_code == 422

def test_conversion_failure_keeps_preparation(client, prepared):
    data, _ = prepared
    with patch('app.administration.compensatory_notes.convert_to_pdf', side_effect=OfficeConversionError('Motor no disponible')):
        response = client.post(URL, data=data)
    assert response.status_code == 503
    assert 'Motor no disponible' in response.text and data['filas-0-fecha_libre'] in response.text


def test_office_timeout_returns_control_and_cleans_temporary_files(app, tmp_path):
    original = app.instance_path
    app.instance_path = str(tmp_path)
    try:
        with app.app_context(), patch('app.administration.office_documents.shutil.which', return_value='soffice'), \
                patch('app.administration.office_documents.subprocess.run',
                      side_effect=subprocess.TimeoutExpired('office', 90)) as runner:
            with pytest.raises(OfficeConversionError):
                convert_to_pdf(b'PK-test', '.docx')
            assert runner.call_args.kwargs['stdout'] == subprocess.DEVNULL
            assert runner.call_args.kwargs['stderr'] == subprocess.DEVNULL
        assert not list((tmp_path / 'impresion_temporal').iterdir())
    finally:
        app.instance_path = original
