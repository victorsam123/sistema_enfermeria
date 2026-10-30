"""Creación idempotente, consultas paginadas y filtros con parámetros SQL."""
from uuid import UUID
from flask import request, url_for
from sqlalchemy.dialects.postgresql import insert
from app.extensions import db
from app.security.permissions import can
from app.hospital_services.classification import audit
from app.administration.forms import RecordFilters


class SubmissionConflict(Exception):
    pass


def create_record(model, values, user_id, request_id):
    """Una clave de envío solo crea una fila, incluso con envíos concurrentes.

    No se impone unicidad sobre nombres/fechas: un formulario nuevo puede
    registrar datos iguales de manera legítima.
    """
    request_id = UUID(request_id)
    statement = insert(model).values(**values, usuario_registro_id=user_id, solicitud_id=request_id)
    record_id = db.session.execute(statement.on_conflict_do_nothing(
        index_elements=['solicitud_id']).returning(model.id)).scalar_one_or_none()
    if record_id is None:
        existing = db.session.scalar(db.select(model).where(model.solicitud_id == request_id))
        if (not existing or existing.usuario_registro_id != user_id
                or any(getattr(existing, key) != value for key, value in values.items())):
            db.session.rollback()
            raise SubmissionConflict('Este formulario ya fue utilizado con otros datos. Abre un nuevo formulario para continuar.')
    if record_id is not None:
        audit('REGISTRO_CREADO', model.__tablename__, record_id, user_id=user_id)
    from app.documents.service import attach_form
    attach_form(model, record_id or existing.id, user_id, request_id, replay=record_id is None)
    db.session.commit()
    return record_id is not None


def filtered_records(model, date_column, name_columns, base_query=None):
    if not can('records.read'):
        return None, None, None, True
    filters = RecordFilters(formdata=request.args, meta={'csrf': False})
    query = base_query if base_query is not None else db.select(model)
    query = query.where(model.eliminado.is_(False))
    valid = filters.validate()
    if valid:
        if filters.q.data:
            # autoescape evita interpretar % y _ introducidos como comodines.
            query = query.where(db.or_(*(column.icontains(filters.q.data, autoescape=True) for column in name_columns)))
        if filters.desde.data:
            query = query.where(date_column >= filters.desde.data)
        if filters.hasta.data:
            query = query.where(date_column <= filters.hasta.data)
    else:
        query = query.where(db.false())
    page = max(1, request.args.get('page', 1, type=int))
    records = db.paginate(query.order_by(date_column.desc(), model.id.desc()),
                          page=page, per_page=20, error_out=False)

    def page_url(number):
        args = {key: request.args[key] for key in ('q', 'desde', 'hasta') if key in request.args}
        args['page'] = number
        args.update(request.view_args or {})
        return url_for(request.endpoint, **args)

    return filters, records, page_url, valid
