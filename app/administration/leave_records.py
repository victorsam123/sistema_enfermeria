"""Flujo compartido exclusivamente por los dos módulos de la actualización 4."""
from dataclasses import dataclass
from uuid import uuid4
from app.documents.service import attach_form
from app.documents.storage import DocumentError, StorageError
from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from app.extensions import db
from app.security.permissions import can
from app.administration.record_access import loading_confirmation
from app.hospital_services.classification import apply_service, saved_message, audit
from app.models import utcnow
from app.administration.leave_forms import LeaveFilters
from app.administration.services import create_record, SubmissionConflict
from app.administration.vacation_rules import vacation_days


@dataclass(frozen=True)
class RecordModule:
    model: type
    form: type
    endpoint: str
    template: str
    title: str
    fields: tuple
    date_field: str
    created_message: str
    updated_message: str
    vacation: bool = False


def listing(module):
    if not can('records.read'):
        return None, None, None, True
    filters = LeaveFilters(formdata=request.args, meta={'csrf': False})
    if 'orden' not in request.args:
        filters.orden.data = 'asc' if module.vacation else 'desc'
    model = module.model
    date_column = getattr(model, module.date_field)
    query = db.select(model).where(model.eliminado.is_(False))
    valid = filters.validate()
    if valid:
        if filters.q.data:
            query = query.where(model.nombres_apellidos.icontains(filters.q.data, autoescape=True))
        if filters.desde.data:
            # En vacaciones el filtro incluye períodos que se superponen al rango.
            end_column = model.fecha_termino if module.vacation else date_column
            query = query.where(end_column >= filters.desde.data)
        if filters.hasta.data:
            query = query.where(date_column <= filters.hasta.data)
    else:
        query = query.where(db.false())
    order = date_column.asc() if filters.orden.data == 'asc' else date_column.desc()
    page = max(1, request.args.get('page', 1, type=int))
    records = db.paginate(query.order_by(order, model.id.asc()), page=page, per_page=20, error_out=False)

    def page_url(number):
        args = {key: request.args[key] for key in ('q', 'desde', 'hasta', 'orden') if key in request.args}
        args['page'] = number
        return url_for(module.endpoint + '.index', **args)

    return filters, records, page_url, valid


def record_page(module, record=None):
    form = module.form(obj=record)
    if request.method == 'GET' and record:
        form.version.data = str(record.version)
    error, status = None, 200
    if form.validate_on_submit():
        values = {field: getattr(form, field).data for field in module.fields}
        if module.vacation:
            # total_dias recibido del navegador se ignora por completo.
            values['total_dias'] = vacation_days(values['fecha_inicio'], values['fecha_termino'])
        values['servicio_id'] = form.servicio_id.data
        from app.employees.lookup import record_links
        values.update(record_links(form))
        try:
            if record:
                if request.form.get('version') != str(record.version):
                    raise StaleDataError()
                apply_service(record, values['servicio_id'], current_user.id)
                for key, value in values.items():
                    setattr(record, key, value)
                record.usuario_modificacion_id = current_user.id
                record.fecha_modificacion = utcnow()
                audit('REGISTRO_MODIFICADO', record.__tablename__, record.id)
                attach_form(type(record), record.id, current_user.id)
                db.session.commit()
                flash(module.updated_message, 'success')
            else:
                created = create_record(module.model, values, current_user.id, form.solicitud_id.data)
                confirmation = loading_confirmation(module.model, form.solicitud_id.data, module.endpoint + '.index')
                if confirmation is not None:
                    return confirmation
                flash(module.created_message if created else 'Este registro ya fue guardado. No se duplicó la carga.', 'success')
            flash(saved_message(form.servicio_id.data), 'success')
            return redirect(url_for(module.endpoint + '.index') + '#registros', code=303)
        except DocumentError as exc:
            db.session.rollback()
            error, status = str(exc), 503 if isinstance(exc, StorageError) else 422
        except SubmissionConflict as exc:
            form.solicitud_id.data = str(uuid4())
            error, status = str(exc), 409
        except StaleDataError:
            db.session.rollback()
            error, status = 'Otro envío modificó este registro. Recarga la página y revisa sus datos antes de editarlo.', 409
        except SQLAlchemyError as exc:
            db.session.rollback()
            current_app.logger.error('Error al guardar en %s (%s)', module.endpoint, type(exc).__name__)
            error, status = 'No se pudo guardar el registro. Tus datos permanecen en el formulario; vuelve a intentarlo.', 503
    elif request.method == 'POST':
        status = 422
    display_total = None
    if module.vacation:
        try:
            display_total = vacation_days(form.fecha_inicio.data, form.fecha_termino.data)
        except ValueError:
            pass
    filters, records, page_url, valid = listing(module)
    return render_template(module.template, form=form, record=record, page_title=module.title,
        filters=filters, records=records, page_url=page_url, save_error=error,
        display_total=display_total), status if valid else 400
