from io import BytesIO
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import re
import pytest
from PIL import Image
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from unittest.mock import patch
from app import create_app
from app.extensions import db
from app.models.documents import DocumentoAdjunto
from app.models.administration import Justificativo, CambioGuardia, DetalleCambioGuardia
from app.models.reposos import Reposo
from app.models.leave_records import Vacacion, Comisionado
from app.models.hospital_services import HistorialAdministrativo
from app.documents.storage import LocalStorage, StorageError
from app.documents.images import prepare_photo
from app.documents.service import read_document
from werkzeug.datastructures import FileStorage
from test_users_rbac import accounts, client_for, PATHS
from test_auth import login
from test_administration import JUST_DATA, form_values
from test_record_helpers import associate_employee


def photo(fmt='PNG', color='white', name=None):
    out = BytesIO()
    Image.new('RGB', (160, 220), color).save(out, fmt)
    return out.getvalue(), name or ('foto.' + {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}[fmt])


def fields(client, url, data=None):
    result = dict(data or {})
    page = client.get(url)
    assert page.status_code == 200, (url, page.status_code)
    for name in ('csrf_token', 'solicitud_id', 'adjuntos_lote', 'version'):
        match = re.search(r'name="' + name + r'"[^>]*value="([^"]*)"', page.text)
        if match:
            result[name] = match.group(1)
    result.setdefault('servicio_id', '1')
    return result


def upload(client, url, data, photos):
    return client.post(url, data={**data, 'fotografias': [(BytesIO(raw), name) for raw, name in photos]}, content_type='multipart/form-data')


@pytest.fixture(autouse=True)
def isolated_documents(app, accounts, tmp_path):
    old = app.extensions['document_storage']
    app.extensions['document_storage'] = LocalStorage(tmp_path / 'private')
    with app.app_context():
        for model in (DocumentoAdjunto, HistorialAdministrativo, DetalleCambioGuardia, CambioGuardia, Justificativo, Reposo, Vacacion, Comisionado):
            db.session.execute(db.delete(model))
        db.session.commit()
    yield
    with app.app_context():
        db.session.rollback()
        db.session.execute(db.delete(DocumentoAdjunto))
        db.session.commit()
    app.extensions['document_storage'] = old


@pytest.mark.parametrize('path,data,model,key', PATHS)
@pytest.mark.parametrize('role', ['SUPERADMIN', 'JEFATURA', 'OPERADOR', 'SUPERVISOR'])
def test_all_forms_save_real_photos_atomically(app, accounts, path, data, model, key, role):
    client = client_for(app, accounts, role)
    data = fields(client, path, data)
    data = associate_employee(app, data, model, key, accounts[0][role][0])
    photos = [photo('PNG', 'white'), photo('JPEG', 'blue'), photo('WEBP', 'red')]
    response = upload(client, path, data, photos)
    assert response.status_code == 303, response.text
    with app.app_context():
        record = db.session.scalar(db.select(model))
        docs = db.session.scalars(db.select(DocumentoAdjunto).order_by(DocumentoAdjunto.id)).all()
        assert record.documentos_count == 3 and len(docs) == 3
        assert all(d.registro_id == record.id and d.tipo_modulo == key and d.usuario_carga_id == accounts[0][role][0] for d in docs)
        for doc, (raw, _) in zip(docs, photos):
            assert read_document(doc, True) == raw
            assert doc.sha256 == sha256(raw).hexdigest()
            assert 'foto' not in doc.ruta_almacenamiento
        assert db.session.scalar(db.select(db.func.count()).select_from(HistorialAdministrativo).where(HistorialAdministrativo.evento == 'DOCUMENTO_ADJUNTADO')) == 3
        rid, did = record.id, docs[0].id
    if role in ('OPERADOR', 'SUPERVISOR'):
        assert client.get(f'/documentos/{key}/{rid}/').status_code == 403
        assert client.get(f'/documentos/{key}/{rid}/{did}/vista').status_code == 403
        assert client.post(f'/documentos/{key}/{rid}/', data=fields(client, path)).status_code == 403
        confirmation = client.get(response.location).text
        assert 'VER DOCUMENTOS ADJUNTOS' not in confirmation
    else:
        gallery = client.get(f'/documentos/{key}/{rid}/')
        assert gallery.status_code == 200 and 'AGREGAR OTRA FOTOGRAFÍA' in gallery.text
        assert client.get(f'/documentos/{key}/{rid}/{did}/vista').mimetype == 'image/jpeg'
        download = client.get(f'/documentos/{key}/{rid}/{did}/descargar')
        assert download.status_code == 200 and download.data == photos[0][0]
        assert 'attachment;' in download.headers['Content-Disposition'] and 'foto' not in download.headers['Content-Disposition']
        assert download.headers['Cache-Control'] == 'no-store'


def create_just(client, photos=()):
    response = upload(client, '/justificativos/', fields(client, '/justificativos/', JUST_DATA), photos)
    assert response.status_code == 303, response.text
    with client.application.app_context():
        return db.session.scalar(db.select(Justificativo.id).order_by(Justificativo.id.desc()))


def test_existing_record_add_retire_history_and_persistence(app, accounts):
    client = client_for(app, accounts, 'JEFATURA')
    rid = create_just(client)
    url = f'/documentos/justificativos/{rid}/'
    with app.app_context():
        row = db.session.get(Justificativo, rid)
        original = (row.solicitud_id, row.version, row.fecha_modificacion, row.usuario_registro_id)
    data = fields(client, url)
    images = [photo('PNG', color=c) for c in ('red', 'blue', 'white', 'black', 'green')]
    assert upload(client, url, data, images).status_code == 303
    assert upload(client, url, data, images).status_code == 303  # mismo lote: sin duplicar
    assert upload(client, url, fields(client, url), [photo('PNG', 'yellow')]).status_code == 422
    with app.app_context():
        row = db.session.get(Justificativo, rid)
        assert (row.solicitud_id, row.version, row.fecha_modificacion, row.usuario_registro_id) == original
        docs = db.session.scalars(db.select(DocumentoAdjunto).order_by(DocumentoAdjunto.id)).all()
        did, key = docs[0].id, docs[0].ruta_almacenamiento
    retire = f'/documentos/justificativos/{rid}/{did}/retirar'
    assert client.get(retire).status_code == 200
    assert client.post(retire, data={**fields(client, retire), 'motivo': 'Documento sustituido por copia legible'}).status_code == 303
    assert client.get(f'/documentos/justificativos/{rid}/{did}/vista').status_code == 404
    assert app.extensions['document_storage'].path(key).is_file()
    assert 'Documento sustituido' in client.get(url + '?historial=1').text
    assert upload(client, url, fields(client, url), [photo('PNG', 'yellow')]).status_code == 303
    with app.app_context():
        assert db.session.get(Justificativo, rid).documentos_count == 5
        assert db.session.scalar(db.select(db.func.count()).select_from(DocumentoAdjunto)) == 6
    # Una nueva aplicación/sesión ve la misma metadata y archivos persistentes.
    fresh = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': app.config['SQLALCHEMY_DATABASE_URI'],
        'SECRET_KEY': app.config['SECRET_KEY'], 'SESSION_COOKIE_SECURE': False,
        'DOCUMENT_LOCAL_ROOT': str(app.extensions['document_storage'].root)})
    fresh_client = fresh.test_client()
    assert login(fresh_client).status_code == 302
    assert fresh_client.get(url).status_code == 200
    with fresh.app_context():
        active_id = db.session.scalar(db.select(DocumentoAdjunto.id).where(DocumentoAdjunto.activo.is_(True)).order_by(DocumentoAdjunto.id.desc()))
    assert fresh_client.get(f'/documentos/justificativos/{rid}/{active_id}/vista').status_code == 200
    assert fresh_client.get(f'/documentos/justificativos/{rid}/{active_id}/descargar').data == photo('PNG', 'yellow')[0]


@pytest.mark.parametrize('bad', ['fake', 'svg', 'heic', 'mismatch', 'damaged', 'animation', 'large', 'many', 'duplicate'])
def test_invalid_photos_never_save_a_record(app, accounts, bad):
    client = client_for(app, accounts, 'SUPERADMIN')
    photos = [photo()]
    if bad == 'fake': photos = [(b'MZ executable', 'foto.jpg')]
    if bad == 'svg': photos = [(b'<svg onload="alert(1)"></svg>', 'foto.svg')]
    if bad == 'heic': photos = [(b'heic', 'foto.heic')]
    if bad == 'mismatch': photos = [(photo()[0], 'foto.jpg')]
    if bad == 'damaged': photos = [(photo()[0][:40], 'foto.png')]
    if bad == 'large': photos = [(b'x' * (app.config['DOCUMENT_MAX_BYTES'] + 1), 'foto.png')]
    if bad == 'many': photos = [photo()] * 6
    if bad == 'duplicate': photos = [photo()] * 2
    if bad == 'animation':
        out = BytesIO(); frames = [Image.new('RGB', (20, 20), c) for c in ('red', 'blue')]
        frames[0].save(out, 'PNG', save_all=True, append_images=frames[1:]); photos = [(out.getvalue(), 'animated.png')]
    result = upload(client, '/justificativos/', fields(client, '/justificativos/', JUST_DATA), photos)
    assert result.status_code == 422, result.status_code
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Justificativo)) == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(DocumentoAdjunto)) == 0
    assert list(app.extensions['document_storage'].objects()) == []


def test_failed_storage_and_failed_database_compensate_objects(app, accounts):
    client = client_for(app, accounts, 'SUPERADMIN')
    backend = app.extensions['document_storage']
    put = backend.put
    calls = []
    def fail_second(key, data, mime):
        calls.append(key); put(key, data, mime)
        if len(calls) == 2: raise OSError('simulated storage interruption after PUT')
    data = fields(client, '/justificativos/', JUST_DATA)
    with patch.object(backend, 'put', side_effect=fail_second):
        assert upload(client, '/justificativos/', data, [photo()]).status_code == 503
    assert list(backend.objects()) == []
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Justificativo)) == 0
    data = fields(client, '/justificativos/', JUST_DATA)
    with patch.object(db.session, 'commit', side_effect=SQLAlchemyError('simulated commit error')):
        assert upload(client, '/justificativos/', data, [photo()]).status_code == 503
    assert list(backend.objects()) == []
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(DocumentoAdjunto)) == 0


def test_record_isolation_csrf_and_duplicate_retry(app, accounts):
    client = client_for(app, accounts, 'SUPERADMIN')
    data = fields(client, '/justificativos/', JUST_DATA)
    assert upload(client, '/justificativos/', data, [photo()]).status_code == 303
    assert upload(client, '/justificativos/', data, [photo()]).status_code == 303
    assert upload(client, '/justificativos/', data, [photo('PNG', 'red')]).status_code == 422
    second = create_just(client)
    with app.app_context():
        doc = db.session.scalar(db.select(DocumentoAdjunto)); rid, did = doc.registro_id, doc.id
        assert db.session.scalar(db.select(db.func.count()).select_from(DocumentoAdjunto)) == 1
    assert client.get(f'/documentos/justificativos/{second}/{did}/vista').status_code == 404
    assert client.get(f'/documentos/reposos/{rid}/{did}/vista').status_code == 404
    assert app.test_client().get(f'/documentos/justificativos/{rid}/{did}/vista').status_code == 302
    assert client.post(f'/documentos/justificativos/{rid}/{did}/retirar', data={'motivo': 'Retiro'}).status_code == 400
    assert client.post(f'/documentos/justificativos/{rid}/', data={}).status_code == 400


def test_database_rejects_orphans_and_owner_reassignment(app, accounts):
    client = client_for(app, accounts, 'SUPERADMIN')
    rid = create_just(client, [photo()]); second = create_just(client)
    with app.app_context():
        doc = db.session.scalar(db.select(DocumentoAdjunto))
        did = doc.id
        for changes in ('registro_id=999999999', f'justificativo_id={second},registro_id={second}', "tipo_modulo='reposos'", 'activo=false'):
            with pytest.raises(SQLAlchemyError):
                db.session.execute(db.text(f'UPDATE documentos_adjuntos SET {changes} WHERE id=:id'), {'id': did})
                db.session.commit()
            db.session.rollback()
        # FK y CHECK también protegen INSERT SQL, sin depender del ORM.
        columns = ['tipo_modulo','registro_id','justificativo_id','reposo_id','nombre_original','nombre_almacenamiento','tipo_mime','tamano_bytes','ruta_almacenamiento','ruta_vista','sha256','sha256_vista','almacenamiento','lote_id','orden_lote','usuario_carga_id']
        values = {c: getattr(db.session.get(DocumentoAdjunto, did), c) for c in columns}
        values.update(justificativo_id=999999999, registro_id=999999999, nombre_almacenamiento=uuid4().hex,
            ruta_almacenamiento=uuid4().hex, ruta_vista=uuid4().hex, lote_id=uuid4())
        with pytest.raises(IntegrityError):
            db.session.execute(db.insert(DocumentoAdjunto).values(**values)); db.session.commit()
        db.session.rollback()


def test_preview_removes_metadata_and_limits_pixels(app):
    out = BytesIO(); image = Image.new('RGB', (3000, 30), 'white'); exif = Image.Exif(); exif[270] = 'private diagnosis'
    image.save(out, 'JPEG', exif=exif)
    with app.app_context():
        prepared = prepare_photo(FileStorage(stream=BytesIO(out.getvalue()), filename='persona.jpg'))
        assert prepared.original == out.getvalue()
        with Image.open(BytesIO(prepared.preview)) as img:
            assert max(img.size) <= app.config['DOCUMENT_PREVIEW_EDGE'] and not img.getexif()
        with patch.dict(app.config, DOCUMENT_MAX_PIXELS=10):
            with pytest.raises(ValueError, match='resolución'):
                prepare_photo(FileStorage(stream=BytesIO(out.getvalue()), filename='a.jpg'))


def test_tampered_storage_is_not_served(app, accounts):
    client = client_for(app, accounts, 'SUPERADMIN'); rid = create_just(client, [photo()])
    with app.app_context():
        doc = db.session.scalar(db.select(DocumentoAdjunto)); did, key = doc.id, doc.ruta_vista
    app.extensions['document_storage'].path(key).write_bytes(b'corrupted')
    assert client.get(f'/documentos/justificativos/{rid}/{did}/vista').status_code == 503


def test_service_is_required_with_photos(app, accounts):
    client = client_for(app, accounts, 'OPERADOR')
    data = fields(client, '/justificativos/', JUST_DATA); data['servicio_id'] = '0'
    assert upload(client, '/justificativos/', data, [photo()]).status_code == 422
    assert list(app.extensions['document_storage'].objects()) == []


def test_runtime_storage_checks_fail_closed(app):
    from app.documents.storage import configure_storage
    with patch.dict(app.config, PRODUCTION=True, DOCUMENT_STORAGE_BACKEND='local', DOCUMENT_LOCAL_PERSISTENT=False):
        with pytest.raises(RuntimeError, match='producción'): configure_storage(app)
    with patch.dict(app.config, DOCUMENT_STORAGE_BACKEND='s3', DOCUMENT_S3_BUCKET=''):
        with pytest.raises(RuntimeError, match='bucket'): configure_storage(app)
    with patch.dict(app.config, DOCUMENT_LOCAL_ROOT=app.static_folder):
        with pytest.raises(RuntimeError, match='privada'): configure_storage(app)


def test_s3_adapter_uses_private_objects_and_bounded_reads(app):
    import boto3
    from botocore.stub import Stubber
    from botocore.response import StreamingBody
    from app.documents.storage import S3Storage
    client = boto3.client('s3', region_name='us-east-1', aws_access_key_id='test-only', aws_secret_access_key='test-only')
    cfg = dict(app.config, DOCUMENT_S3_BUCKET='hospital-test', DOCUMENT_S3_SSE='AES256')
    with patch('boto3.client', return_value=client):
        backend = S3Storage(cfg)
    key = 'documentos/' + 'a' * 32 + '/original.png'
    raw = photo()[0]
    with Stubber(client) as stub:
        stub.add_response('put_object', {'ETag': 'test'}, {'Bucket': 'hospital-test', 'Key': key, 'Body': raw,
            'ContentType': 'image/png', 'CacheControl': 'private, no-store', 'ServerSideEncryption': 'AES256'})
        stub.add_response('get_object', {'Body': StreamingBody(BytesIO(raw), len(raw))}, {'Bucket': 'hospital-test', 'Key': key})
        stub.add_response('delete_object', {}, {'Bucket': 'hospital-test', 'Key': key})
        backend.put(key, raw, 'image/png')
        assert backend.get(key, 8 * 1024 * 1024) == raw
        backend.delete(key)
        stub.assert_no_pending_responses()
    with pytest.raises(StorageError): backend.get('../escape', 100)


def test_folder_and_excel_attachment_indicators(app, accounts):
    from test_service_files_reports import report, workbook
    client = client_for(app, accounts, 'SUPERADMIN'); rid = create_just(client, [photo(), photo('PNG', 'red')])
    folder = client.get('/archivos-por-servicio/1/justificativos/')
    assert folder.status_code == 200
    assert '2 fotografías' in folder.text and f'/documentos/justificativos/{rid}/' in folder.text
    archive, sheets, data = workbook(report(client))
    main = data[sheets[0]]['cells']
    assert main['A6'] == 'CAMBIO DE GUARDIA' and main['G6'] == 'JUSTIFICATIVO' and main['K6'] == 'REPOSO'
    complement = data[next(s for s in sheets if s.endswith('_JUST'))]['cells']
    assert complement['K7'] == 'DOCUMENTOS ADJUNTOS' and complement['L7'] == 'Cantidad de fotografías'
    assert complement['K8'] == 'Sí' and complement['L8'] == '2'
    assert not any(name.startswith('xl/media/') for name in archive.namelist())


def test_concurrent_additions_respect_total_limit(app, accounts):
    from concurrent.futures import ThreadPoolExecutor
    from app.documents.service import attach
    from app.documents.storage import DocumentError
    client = client_for(app, accounts, 'SUPERADMIN')
    rid = create_just(client, [photo('PNG', c) for c in ('red', 'blue', 'white', 'black')])
    uid = accounts[0]['SUPERADMIN'][0]
    def add(color):
        with app.app_context():
            raw, name = photo('PNG', color)
            prepared = prepare_photo(FileStorage(stream=BytesIO(raw), filename=name))
            record = db.session.get(Justificativo, rid)
            try:
                attach(record, [prepared], uuid4(), uid)
                db.session.commit()
                return True
            except DocumentError:
                db.session.rollback()
                return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(add, ('green', 'yellow')))
    assert sorted(results) == [False, True]
    with app.app_context():
        assert db.session.get(Justificativo, rid).documentos_count == 5


def test_conciliation_keeps_retained_objects_and_removes_only_old_orphans(app, accounts):
    import os, time
    from app.documents.maintenance import reconcile
    client = client_for(app, accounts, 'SUPERADMIN'); rid = create_just(client, [photo()])
    backend = app.extensions['document_storage']
    old = 'documentos/' + 'b'*32 + '/original.png'
    recent = 'documentos/' + 'c'*32 + '/original.png'
    backend.put(old, photo()[0], 'image/png'); backend.put(recent, photo()[0], 'image/png')
    os.utime(backend.path(old), (time.time()-90000,)*2)
    with app.app_context():
        result = reconcile()
        assert result['sin_referencia'] == 2 and result['huerfanos_retirados'] == 0
        result = reconcile(clean=True, verify=True)
        assert result['huerfanos_retirados'] == 1 and result['referencias'] == 2 and not result['integridad_fallida']
        assert db.session.get(Justificativo, rid).documentos_count == 1
    assert not backend.path(old).exists() and backend.path(recent).exists()


def test_backup_copies_originals_views_and_retired_documents(app, accounts, tmp_path):
    import json
    from pathlib import Path
    from types import SimpleNamespace
    from scripts.respaldar_documentos import main
    client = client_for(app, accounts, 'SUPERADMIN'); rid = create_just(client, [photo(), photo('PNG','red')])
    with app.app_context():
        did = db.session.scalar(db.select(DocumentoAdjunto.id).order_by(DocumentoAdjunto.id))
    retire = f'/documentos/justificativos/{rid}/{did}/retirar'
    assert client.post(retire, data={**fields(client,retire),'motivo':'Copia sustituida'}).status_code == 303
    destination = tmp_path / 'backup'
    def fake_run(arguments, **kwargs):
        if arguments[0] == 'pg_dump':
            dump = Path(arguments[arguments.index('--file') + 1])
            dump.write_bytes(b'fake PostgreSQL backup for test')
        return SimpleNamespace(returncode=0)
    with patch('scripts.respaldar_documentos.create_app',return_value=app), \
            patch.dict('os.environ', {'PG_DUMP': 'pg_dump'}), \
            patch('scripts.respaldar_documentos.subprocess.run', side_effect=fake_run):
        main(destination)
    folder = next(destination.iterdir())
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['archivos']) == 4
    assert sha256((folder/'postgres.dump').read_bytes()).hexdigest() == manifest['postgres_sha256']
    for item in manifest['archivos']:
        assert sha256((folder/'objetos'/item['key']).read_bytes()).hexdigest() == item['sha256']


def test_soft_deleted_record_hides_documents_and_restoration_preserves_them(app, accounts):
    client=client_for(app,accounts,'SUPERADMIN'); rid=create_just(client,[photo()])
    with app.app_context():
        did=db.session.scalar(db.select(DocumentoAdjunto.id))
    delete=f'/registros/justificativos/{rid}/eliminar'
    assert client.post(delete,data={**fields(client,delete),'motivo':'Carga anulada','confirmacion':'CONFIRMAR'}).status_code==303
    for suffix in ('',f'{did}/vista',f'{did}/descargar',f'{did}/retirar'):
        assert client.get(f'/documentos/justificativos/{rid}/'+suffix).status_code==404
    with app.app_context():
        row=db.session.get(Justificativo,rid); version=row.version
        assert db.session.get(DocumentoAdjunto,did).activo
    assert client.post(f'/registros/justificativos/{rid}/restaurar',data={**fields(client,'/registros/eliminados'),'version':str(version)}).status_code==303
    assert client.get(f'/documentos/justificativos/{rid}/{did}/vista').status_code==200


def test_guardia_document_category_cannot_be_forged(app, accounts):
    path,data,model,key=PATHS[2]
    client=client_for(app,accounts,'SUPERADMIN')
    assert upload(client,path,fields(client,path,data),[photo()]).status_code==303
    with app.app_context():
        row=db.session.scalar(db.select(CambioGuardia)); rid=row.id
        doc=db.session.scalar(db.select(DocumentoAdjunto)); did=doc.id
        for sql in ("UPDATE documentos_adjuntos SET tipo_modulo='pagadas' WHERE id=:id",
                    "UPDATE cambios_guardia SET tipo_cambio='PAGADA' WHERE id=:id"):
            with pytest.raises(SQLAlchemyError):
                db.session.execute(db.text(sql),{'id':did if 'documentos' in sql else rid}); db.session.commit()
            db.session.rollback()
    assert client.get(f'/documentos/pagadas/{rid}/{did}/vista').status_code==404
