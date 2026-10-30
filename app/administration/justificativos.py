from uuid import uuid4
from app.documents.service import attach_form
from app.documents.storage import DocumentError, StorageError
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from app.extensions import db
from app.hospital_services.classification import apply_service, saved_message, audit
from app.models import utcnow
from app.models.administration import Justificativo
from app.security.permissions import permission_required, can
from app.administration.record_access import get_live_record, loading_confirmation
from app.administration.forms import JustificativoForm
from app.administration.services import create_record, filtered_records, SubmissionConflict

bp = Blueprint('justificativos', __name__, url_prefix='/justificativos')
FIELDS = ('nombres_apellidos', 'fecha_inasistencia', 'motivo', 'fecha_cobertura')


@bp.route('/', methods=['GET', 'POST'])
@permission_required('records.create')
def index():
    return justificativo_page()


@bp.route('/<int:record_id>/editar', methods=['GET', 'POST'])
@permission_required('records.edit')
def edit(record_id):
    return justificativo_page(get_live_record(Justificativo, record_id))


def justificativo_page(record=None):
    form = JustificativoForm(obj=record)
    if request.method == 'GET' and record:
        form.version.data = str(record.version)
    error, status = None, 200
    if form.validate_on_submit():
        values = {field: getattr(form, field).data for field in FIELDS}
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
                flash('Justificativo actualizado correctamente', 'success')
            else:
                created = create_record(Justificativo, values, current_user.id, form.solicitud_id.data)
                confirmation = loading_confirmation(Justificativo, form.solicitud_id.data, 'justificativos.index')
                if confirmation is not None:
                    return confirmation
                flash('Justificativo registrado correctamente' if created else 'Este justificativo ya fue registrado. No se duplicó la carga.', 'success')
            flash(saved_message(form.servicio_id.data), 'success')
            return redirect(url_for('justificativos.index') + '#registros', code=303)
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
            current_app.logger.error('Error al guardar justificativo (%s)', type(exc).__name__)
            error, status = 'No se pudo guardar el justificativo. Tus datos permanecen en el formulario; vuelve a intentarlo.', 503
    elif request.method == 'POST':
        status = 422
    filters, records, page_url, filters_valid = filtered_records(
        Justificativo, Justificativo.fecha_inasistencia, [Justificativo.nombres_apellidos])
    return render_template('administration/justificativos.html', form=form, record=record,
        filters=filters, records=records, page_url=page_url, save_error=error,
        page_title='Editar justificativo' if record else 'Justificativo'), status if filters_valid else 400
