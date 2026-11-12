from uuid import UUID
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm.exc import StaleDataError
from app.extensions import db
from app.models import utcnow
from app.models.employees import Funcionario
from app.models.documents import DocumentoAdjunto
from app.hospital_services.classification import audit, apply_service
from app.documents.service import attach
from app.documents.storage import DocumentError

FIELDS = ('nombres', 'apellidos', 'cedula', 'carrera', 'fecha_nacimiento', 'telefono',
    'direccion_actual', 'servicio_id')


def active_photo(record):
    return db.session.scalar(db.select(DocumentoAdjunto).where(DocumentoAdjunto.funcionario_id == record.id,
        DocumentoAdjunto.tipo_modulo == 'funcionarios', DocumentoAdjunto.activo.is_(True)))


def replace_photo(record, photos, batch, user_id):
    if not photos:
        return
    if len(photos) != 1:
        raise DocumentError('Selecciona una sola fotografía personal.')
    # El bloqueo se comparte con la conciliación y el respaldo documentales.
    db.session.execute(db.text('SELECT pg_advisory_xact_lock_shared(901,9)'))
    current = active_photo(record)
    prior_batch = db.session.scalar(db.select(DocumentoAdjunto).where(
        DocumentoAdjunto.funcionario_id == record.id, DocumentoAdjunto.lote_id == UUID(str(batch))))
    if prior_batch:
        if prior_batch.sha256 != photos[0].digest:
            raise DocumentError('Este envío ya fue utilizado con otra fotografía. Recarga la ficha.')
        return
    if current and current.sha256 == photos[0].digest:
        return
    if current:
        current.activo, current.fecha_retiro = False, utcnow()
        current.usuario_retiro_id = user_id
        current.motivo_retiro = 'Sustitución autorizada de fotografía personal.'
        audit('DOCUMENTO_RETIRADO', 'funcionarios', record.id, user_id=user_id,
              details={'documento_id': current.id, 'motivo': current.motivo_retiro})
        db.session.flush()
    attach(record, photos, batch, user_id)
    current = active_photo(record)
    record.foto_ruta = current.ruta_vista
    audit('FUNCIONARIO_FOTO_ACTUALIZADA', 'funcionarios', record.id, user_id=user_id,
          details={'documento_id': current.id})


def create_employee(values, photos, request_id, user_id):
    identifier = db.session.execute(insert(Funcionario).values(**values, usuario_registro_id=user_id,
        solicitud_id=UUID(request_id)).on_conflict_do_nothing(index_elements=['solicitud_id']).returning(Funcionario.id)).scalar_one_or_none()
    if identifier is None:
        record = db.session.scalar(db.select(Funcionario).where(Funcionario.solicitud_id == UUID(request_id)))
        if record.usuario_registro_id != user_id or any(getattr(record, key) != value for key, value in values.items()):
            raise DocumentError('Este formulario ya fue utilizado con otros datos. Abre un nuevo formulario.')
        existing = db.session.scalar(db.select(DocumentoAdjunto).where(DocumentoAdjunto.funcionario_id == record.id,
            DocumentoAdjunto.lote_id == UUID(request_id)))
        if ([p.digest for p in photos] != ([existing.sha256] if existing else [])):
            raise DocumentError('El formulario ya fue guardado con otra selección de fotografía. Consulta la ficha.')
        return record
    record = db.session.get(Funcionario, identifier)
    from app.employees.employment_services import add_link
    add_link(record.id, values['fecha_ingreso'], user_id, request_id)
    db.session.refresh(record)
    replace_photo(record, photos, request_id, user_id)
    audit('FUNCIONARIO_CREADO', 'funcionarios', record.id, user_id=user_id)
    return record


def locked_employee(record_id, version):
    record = db.session.scalar(db.select(Funcionario).where(Funcionario.id == record_id)
        .with_for_update(of=Funcionario).execution_options(populate_existing=True))
    if record is None or str(record.version) != str(version):
        raise StaleDataError()
    return record


def update_employee(record, values, photos, request_id, user_id):
    changed = [key for key, value in values.items() if getattr(record, key) != value]
    apply_service(record, values['servicio_id'], user_id)
    for key, value in values.items():
        setattr(record, key, value)
    old_photo = record.foto_ruta
    replace_photo(record, photos, request_id, user_id)
    if changed or old_photo != record.foto_ruta:
        record.usuario_modificacion_id, record.fecha_modificacion = user_id, utcnow()
        audit('FUNCIONARIO_MODIFICADO', 'funcionarios', record.id, user_id=user_id,
              details={'campos': changed + (['fotografia'] if old_photo != record.foto_ruta else [])})
