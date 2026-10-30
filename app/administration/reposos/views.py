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
from app.models.reposos import Reposo
from app.administration.reposos.forms import ReposoForm, ReposoFilters
from app.administration.reposos.rules import rest_days
from app.administration.services import create_record, SubmissionConflict

FIELDS = ('nombres_apellidos', 'fecha_desde', 'fecha_hasta', 'diagnostico', 'fecha_entrega_departamento')


def listing():
    if not can('records.read'):
        return None, None, None, True
    filters = ReposoFilters(formdata=request.args, meta={'csrf': False})
    valid = filters.validate()
    query = db.select(Reposo).where(Reposo.eliminado.is_(False))
    if valid:
        if filters.q.data:
            query = query.where(Reposo.nombres_apellidos.icontains(filters.q.data, autoescape=True))
        if filters.desde.data:
            query = query.where(Reposo.fecha_hasta >= filters.desde.data)
        if filters.hasta.data:
            query = query.where(Reposo.fecha_desde <= filters.hasta.data)
    else:
        query = query.where(db.false())
    orders = {
        'desde_desc': Reposo.fecha_desde.desc(), 'desde_asc': Reposo.fecha_desde.asc(),
        'creacion_desc': Reposo.fecha_creacion.desc(), 'creacion_asc': Reposo.fecha_creacion.asc(),
    }
    page = max(1, request.args.get('page', 1, type=int))
    records = db.paginate(query.order_by(orders.get(filters.orden.data, Reposo.fecha_desde.desc()), Reposo.id.asc()),
                          page=page, per_page=20, error_out=False)

    def page_url(number):
        args = {key: request.args[key] for key in ('q', 'desde', 'hasta', 'orden') if key in request.args}
        return url_for('reposo.index', page=number, **args)

    return filters, records, page_url, valid


def reposo_page(record=None):
    form = ReposoForm(obj=record)
    if request.method == 'GET' and record:
        form.version.data = str(record.version)
    error, status = None, 200
    if form.validate_on_submit():
        values = {field: getattr(form, field).data for field in FIELDS}
        # No se lee total_dias del POST: la autoridad es el cálculo Python.
        values['total_dias'] = rest_days(values['fecha_desde'], values['fecha_hasta'])
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
                flash('Reposo actualizado correctamente', 'success')
            else:
                created = create_record(Reposo, values, current_user.id, form.solicitud_id.data)
                confirmation = loading_confirmation(Reposo, form.solicitud_id.data, 'reposo.index')
                if confirmation is not None:
                    return confirmation
                flash('Reposo registrado correctamente' if created else 'Este reposo ya fue registrado. No se duplicó la carga.', 'success')
            flash(saved_message(form.servicio_id.data), 'success')
            return redirect(url_for('reposo.index') + '#registros', code=303)
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
            current_app.logger.error('Error al guardar reposo (%s)', type(exc).__name__)
            error, status = 'No se pudo guardar el reposo. Tus datos permanecen en el formulario; vuelve a intentarlo.', 503
    elif request.method == 'POST':
        status = 422
    try:
        display_total = rest_days(form.fecha_desde.data, form.fecha_hasta.data)
    except ValueError:
        display_total = None
    filters, records, page_url, valid = listing()
    return render_template('administration/reposo.html', page_title='Reposo', record=record,
        form=form, display_total=display_total, save_error=error, filters=filters,
        records=records, page_url=page_url), status if valid else 400
