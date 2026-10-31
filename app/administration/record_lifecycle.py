from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import TextAreaField, HiddenField, SelectField
from wtforms.validators import Length
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from app.extensions import db
from app.models import utcnow
from app.administration.forms import required
from app.hospital_services.records import CATEGORIES
from app.hospital_services.classification import audit
from app.security.permissions import permission_required
from app.administration.guardia_monthly import GuardiaValidation

bp = Blueprint('record_lifecycle', __name__, url_prefix='/registros')


class DeleteForm(FlaskForm):
    motivo = TextAreaField('Motivo de eliminación', filters=[lambda v: (v or '').strip()], validators=[required(), Length(min=3, max=1000)])
    version = HiddenField(validators=[required()])
    confirmacion = SelectField('Confirmación', choices=[('', 'Selecciona una opción'), ('CONFIRMAR', 'Confirmar eliminación lógica')], validators=[required()])


class RestoreForm(FlaskForm):
    version = HiddenField(validators=[required()])


def find_record(key, record_id, locked=False):
    category = CATEGORIES.get(key)
    if not category:
        abort(404)
    query = db.select(category.model).where(category.model.id == record_id)
    if locked:
        query = query.with_for_update(of=category.model).execution_options(populate_existing=True)
    record = db.session.scalar(query)
    if not record or (category.kind and record.tipo_cambio != category.kind):
        abort(404)
    return category, record


@bp.route('/<category_key>/<int:record_id>/eliminar', methods=['GET', 'POST'])
@permission_required('records.delete')
def delete(category_key, record_id):
    category, record = find_record(category_key, record_id)
    if record.eliminado:
        abort(404)
    form = DeleteForm()
    if request.method == 'GET':
        form.version.data = str(record.version)
    status, error = 200, None
    if form.validate_on_submit():
        try:
            category, record = find_record(category_key, record_id, locked=True)
            if form.version.data != str(record.version) or record.eliminado:
                raise StaleDataError()
            if form.confirmacion.data != 'CONFIRMAR':
                abort(400)
            record.eliminado, record.usuario_eliminacion_id = True, current_user.id
            record.fecha_eliminacion, record.motivo_eliminacion = utcnow(), form.motivo.data
            record.usuario_modificacion_id, record.fecha_modificacion = current_user.id, utcnow()
            audit('REGISTRO_ELIMINADO', record.__tablename__, record.id, details={'motivo': form.motivo.data})
            db.session.commit()
            flash('Registro eliminado de las consultas. Los datos permanecen conservados en PostgreSQL.', 'success')
            return redirect(url_for('main.dashboard'), code=303)
        except StaleDataError:
            db.session.rollback()
            status, error = 409, 'El registro fue modificado. Recarga la página antes de eliminarlo.'
        except SQLAlchemyError:
            db.session.rollback()
            status, error = 503, 'No se pudo eliminar el registro. No se modificaron los datos.'
    elif request.method == 'POST':
        status = 422
    return render_template('administration/delete_record.html', page_title='Confirmar eliminación lógica',
        record=record, category=category, form=form, save_error=error), status


@bp.get('/eliminados')
@permission_required('records.restore')
def trash():
    key = request.args.get('categoria', 'justificativos')
    category = CATEGORIES.get(key)
    if not category:
        abort(400)
    query = db.select(category.model).where(category.model.eliminado.is_(True))
    if category.kind:
        query = query.where(category.model.tipo_cambio == category.kind)
    rows = db.paginate(query.order_by(category.model.fecha_eliminacion.desc(), category.model.id.desc()),
        page=max(1, request.args.get('page', 1, type=int)), per_page=20, error_out=False)
    return render_template('administration/trash.html', page_title='Registros eliminados', categories=CATEGORIES,
        category_key=key, category=category, rows=rows, form=RestoreForm())


@bp.post('/<category_key>/<int:record_id>/restaurar')
@permission_required('records.restore')
def restore(category_key, record_id):
    form = RestoreForm()
    if not form.validate_on_submit():
        abort(422)
    try:
        from app.administration.guardia_monthly import lock_monthly, check_monthly, record_values
        from app.models.administration import CambioGuardia
        if CATEGORIES.get(category_key) and CATEGORIES[category_key].model is CambioGuardia:
            lock_monthly()
        category, record = find_record(category_key, record_id, locked=True)
        if form.version.data != str(record.version) or not record.eliminado:
            raise StaleDataError()
        if isinstance(record, CambioGuardia):
            check_monthly(record_values(record), record.fecha_cambio, exclude=record.id)
            from app.administration.guardia_monthly import check_duplicate
            check_duplicate(record_values(record), [dict(participante=d.participante,
                fecha_guardia=d.fecha_guardia, hora_inicio=d.hora_inicio, hora_fin=d.hora_fin,
                codigo=d.codigo) for d in record.detalles], exclude=record.id)
        audit('REGISTRO_RESTAURADO', record.__tablename__, record.id,
            details={'motivo_eliminacion': record.motivo_eliminacion, 'usuario_eliminacion_id': record.usuario_eliminacion_id,
                     'fecha_eliminacion': record.fecha_eliminacion.isoformat()})
        record.eliminado, record.usuario_eliminacion_id, record.fecha_eliminacion, record.motivo_eliminacion = False, None, None, None
        record.usuario_modificacion_id, record.fecha_modificacion = current_user.id, utcnow()
        db.session.commit()
        flash('Registro restaurado correctamente.', 'success')
        return redirect(url_for('record_lifecycle.trash', categoria=category_key), code=303)
    except GuardiaValidation as exc:
        db.session.rollback()
        flash(str(exc), 'error')
        return redirect(url_for('record_lifecycle.trash', categoria=category_key), code=303)
    except StaleDataError:
        db.session.rollback()
        abort(409, description='El registro fue modificado. Recarga la página.')


@bp.get('/<category_key>/<int:record_id>/eliminado')
@permission_required('records.restore')
def archived(category_key, record_id):
    from app.hospital_services.records import matching_details
    category, record = find_record(category_key, record_id)
    if not record.eliminado:
        abort(404)
    return render_template('administration/deleted_record.html', page_title='Detalle del registro eliminado',
        category=category, record=record, matching_details=matching_details)
