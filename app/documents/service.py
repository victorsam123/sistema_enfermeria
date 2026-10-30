"""La metadata se confirma con el registro. Los objetos se compensan al revertir.

PostgreSQL y S3 no comparten un commit distribuido. Ante resultado incierto se
conserva el objeto y se concilia después; nunca se borra un objeto referenciado.
"""
from hashlib import sha256
from uuid import UUID, uuid4
from flask import current_app, g, has_request_context
from sqlalchemy import event
from sqlalchemy.orm import Session
from app.extensions import db
from app.models.documents import DocumentoAdjunto
from app.hospital_services.classification import audit
from app.documents.storage import storage, StorageError, DocumentError

PARENTS = {'justificativos': 'justificativo_id', 'reposos': 'reposo_id', 'cambios_guardia': 'cambio_guardia_id',
           'vacaciones': 'vacacion_id', 'comisionados': 'comisionado_id', 'funcionarios': 'funcionario_id'}


def category_key(record):
    return ('pagadas' if record.tipo_cambio == 'PAGADA' else 'guardias') if record.__tablename__ == 'cambios_guardia' else record.__tablename__


def photo_count(record):
    return db.session.scalar(db.select(db.func.count()).select_from(DocumentoAdjunto).where(
        DocumentoAdjunto.tipo_modulo == category_key(record), DocumentoAdjunto.registro_id == record.id,
        DocumentoAdjunto.activo.is_(True))) or 0


def cleanup_pending(session):
    pending = session.info.pop('document_objects', [])
    for backend, key in pending:
        try:
            # Una pérdida de conexión durante COMMIT puede dejar un resultado
            # incierto. Consultar una conexión nueva antes de compensar.
            with db.engine.connect() as connection:
                exists = connection.scalar(db.select(DocumentoAdjunto.id).where(db.or_(
                    DocumentoAdjunto.ruta_almacenamiento == key, DocumentoAdjunto.ruta_vista == key)).limit(1))
            if not exists:
                backend.delete(key)
        except Exception:
            current_app.logger.error('Compensación de adjuntos pendiente; ejecutar conciliar-documentos. Objeto %s', key)


@event.listens_for(Session, 'after_rollback')
def rollback_objects(session):
    if session.info.get('document_objects'):
        cleanup_pending(session)


@event.listens_for(Session, 'after_commit')
def committed_objects(session):
    session.info.pop('document_objects', None)


def attach(record, photos, batch, user_id, replay=False):
    if not photos and not replay:
        return
    batch = UUID(str(batch))
    db.session.execute(db.text('SELECT pg_advisory_xact_lock_shared(901,9)'))
    model = type(record)
    # La misma fila principal serializa cargas y retiros concurrentes.
    db.session.execute(db.select(model.id).where(model.id == record.id).with_for_update()).scalar_one()
    if record.eliminado:
        raise DocumentError('No se pueden adjuntar documentos a un registro eliminado.')
    key = category_key(record)
    existing = db.session.scalars(db.select(DocumentoAdjunto).where(DocumentoAdjunto.tipo_modulo == key,
        DocumentoAdjunto.registro_id == record.id, DocumentoAdjunto.lote_id == batch).order_by(DocumentoAdjunto.orden_lote)).all()
    if existing or replay:
        if [(p.digest, p.name) for p in photos] != [(d.sha256, d.nombre_original) for d in existing]:
            raise DocumentError('Este envío ya fue utilizado con otros adjuntos. Consulta el registro antes de volver a cargarlo.')
        return
    if photo_count(record) + len(photos) > current_app.config['DOCUMENT_MAX_FILES']:
        raise DocumentError(f"El registro admite hasta {current_app.config['DOCUMENT_MAX_FILES']} fotografías activas.")
    hashes = set(db.session.scalars(db.select(DocumentoAdjunto.sha256).where(DocumentoAdjunto.tipo_modulo == key,
        DocumentoAdjunto.registro_id == record.id, DocumentoAdjunto.activo.is_(True))).all())
    if any(p.digest in hashes for p in photos):
        raise DocumentError('Una de las fotografías ya está adjunta a este registro.')
    backend = storage()
    for order, photo in enumerate(photos):
        identifier = uuid4().hex
        original_key, preview_key = f'documentos/{identifier}/original.{photo.extension}', f'documentos/{identifier}/vista.jpg'
        for object_key, data, mime in ((original_key, photo.original, photo.mime), (preview_key, photo.preview, 'image/jpeg')):
            # Registrar antes del PUT: una respuesta perdida no implica que el
            # proveedor no haya recibido el objeto.
            db.session.info.setdefault('document_objects', []).append((backend, object_key))
            try:
                backend.put(object_key, data, mime)
            except Exception as exc:
                raise StorageError('No se pudo almacenar la fotografía. No se guardó la operación; vuelve a seleccionar las imágenes e inténtalo nuevamente.') from exc
        doc = DocumentoAdjunto(tipo_modulo=key, registro_id=record.id,
            **{PARENTS[record.__tablename__]: record.id}, nombre_original=photo.name,
            nombre_almacenamiento=identifier + '.' + photo.extension, tipo_mime=photo.mime,
            tamano_bytes=len(photo.original), ruta_almacenamiento=original_key, ruta_vista=preview_key,
            sha256=photo.digest, sha256_vista=sha256(photo.preview).hexdigest(),
            almacenamiento=current_app.config['DOCUMENT_STORAGE_BACKEND'], lote_id=batch,
            orden_lote=order, usuario_carga_id=user_id)
        db.session.add(doc)
        db.session.flush()
        audit('DOCUMENTO_ADJUNTADO', record.__tablename__, record.id, user_id=user_id,
              details={'documento_id': doc.id})


def attach_form(model, record_id, user_id, batch=None, replay=False):
    if not has_request_context():
        return
    photos = getattr(g, 'document_photos', [])
    if photos or replay:
        record = db.session.get(model, record_id)
        attach(record, photos, batch or getattr(g, 'document_batch', None), user_id, replay)


def read_document(document, original=False):
    if document.almacenamiento != current_app.config['DOCUMENT_STORAGE_BACKEND']:
        raise StorageError('El documento pertenece a otro almacenamiento. Solicita la migración de archivos al administrador.')
    key = document.ruta_almacenamiento if original else document.ruta_vista
    maximum = max(document.tamano_bytes, 32 * 1024 * 1024)
    try:
        data = storage().get(key, maximum)
        expected = document.sha256 if original else document.sha256_vista
        if sha256(data).hexdigest() != expected:
            raise StorageError('No se pudo verificar la integridad del documento.')
        return data
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError('El documento no está disponible temporalmente. Inténtalo nuevamente.') from exc
