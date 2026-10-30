"""Una transacción conserva la operación y todas sus fechas asociadas."""
from uuid import UUID
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm.exc import StaleDataError
from app.extensions import db
from app.hospital_services.classification import apply_service, audit
from app.models import utcnow
from app.models.administration import CambioGuardia, DetalleCambioGuardia
from app.administration.services import SubmissionConflict


class DetailConflict(ValueError):
    pass


def signature(details):
    return sorted((d['participante'], d['fecha_guardia'], d['hora_inicio'], d['hora_fin'], d['codigo'] or '') for d in details)


def detail_values(form):
    return [dict(detalle_id=int(entry.form.detalle_id.data) if entry.form.detalle_id.data else None,
        participante=entry.form.participante.data, fecha_guardia=entry.form.fecha_guardia.data,
        hora_inicio=entry.form.hora_inicio.data, hora_fin=entry.form.hora_fin.data,
        codigo=entry.form.codigo.data or None) for entry in form.detalles]


def create_guardia(values, details, user_id, request_id):
    if any(d['detalle_id'] for d in details):
        raise DetailConflict('Una carga nueva no puede reutilizar identificadores de fechas guardadas.')
    first = details[0]
    # Columnas anteriores: se conservan como referencia de la carga inicial.
    statement = insert(CambioGuardia).values(**values, usuario_registro_id=user_id,
        solicitud_id=UUID(request_id), fecha_cambio=first['fecha_guardia'],
        hora_inicio=first['hora_inicio'], hora_fin=first['hora_fin'])
    record_id = db.session.execute(statement.on_conflict_do_nothing(
        index_elements=['solicitud_id']).returning(CambioGuardia.id)).scalar_one_or_none()
    if record_id is None:
        existing = db.session.scalar(db.select(CambioGuardia).where(CambioGuardia.solicitud_id == UUID(request_id)))
        stored = [dict(participante=d.participante, fecha_guardia=d.fecha_guardia,
            hora_inicio=d.hora_inicio, hora_fin=d.hora_fin, codigo=d.codigo) for d in existing.detalles] if existing else []
        if (not existing or existing.usuario_registro_id != user_id
                or any(getattr(existing, k) != v for k, v in values.items()) or signature(stored) != signature(details)):
            db.session.rollback()
            raise SubmissionConflict('Este formulario ya fue utilizado con otros datos. Abre una nueva carga para continuar.')
        from app.documents.service import attach_form
        attach_form(CambioGuardia, existing.id, user_id, request_id, replay=True)
        db.session.commit()
        return False
    for order, detail in enumerate(details):
        add_detail(record_id, values, detail, order)
    audit('REGISTRO_CREADO', 'cambios_guardia', record_id, user_id=user_id)
    from app.documents.service import attach_form
    attach_form(CambioGuardia, record_id, user_id, request_id)
    db.session.commit()
    return True


def add_detail(record_id, names, detail, order):
    db.session.add(DetalleCambioGuardia(cambio_guardia_id=record_id, orden=order,
        funcionario=names['solicitante'] if detail['participante'] == 'S' else names['reemplazante'],
        **{k: v for k, v in detail.items() if k != 'detalle_id'}))


def update_guardia(record, names, details, version, user_id):
    if version != str(record.version):
        raise StaleDataError()
    stored = {d.id: d for d in record.detalles}
    incoming = {d['detalle_id'] for d in details if d['detalle_id']}
    if incoming != set(stored):
        raise DetailConflict('Las fechas guardadas deben conservarse y pertenecer a este cambio. Recarga la edición.')
    for values in details:
        previous = stored.get(values['detalle_id'])
        if previous and previous.orden in (0, 1) and values['participante'] != ('S' if previous.orden == 0 else 'R'):
            raise DetailConflict('Las secciones iniciales deben conservar al solicitante y al reemplazante correspondientes.')
    apply_service(record, names['servicio_id'], user_id)
    for key, value in names.items():
        setattr(record, key, value)
    record.usuario_modificacion_id = user_id
    record.fecha_modificacion = utcnow()
    next_order = max((d.orden for d in record.detalles), default=-1) + 1
    for values in details:
        if values['detalle_id']:
            row = stored[values['detalle_id']]
            for key, value in values.items():
                if key != 'detalle_id':
                    setattr(row, key, value)
            row.funcionario = names['solicitante'] if row.participante == 'S' else names['reemplazante']
        else:
            add_detail(record.id, names, values, next_order)
            next_order += 1
    audit('REGISTRO_MODIFICADO', 'cambios_guardia', record.id, user_id=user_id)
    from app.documents.service import attach_form
    attach_form(CambioGuardia, record.id, user_id)
    db.session.commit()
