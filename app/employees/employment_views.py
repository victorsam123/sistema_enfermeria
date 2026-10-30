from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from app.extensions import db
from app.models.employees import Funcionario
from app.models.employment_links import VinculoLaboral
from app.security.permissions import permission_required
from app.employees.employment_forms import EmploymentForm, EmploymentStateForm
from app.employees.employment_services import add_link, update_link, change_state, next_number, validate_entry, EmploymentConflict
from app.employees.rules import paraguay_today, seniority

bp = Blueprint('employment_links', __name__, url_prefix='/funcionarios/<int:record_id>/vinculos')


def find(record_id, link_id=None):
    person = db.get_or_404(Funcionario, record_id)
    link = db.get_or_404(VinculoLaboral, link_id) if link_id is not None else None
    if link and link.funcionario_id != person.id:
        abort(404)
    return person, link


@bp.route('/nuevo', methods=['GET', 'POST'])
@permission_required('employment.manage')
def create(record_id):
    person, _ = find(record_id)
    return link_page(person)


@bp.route('/<int:link_id>/editar', methods=['GET', 'POST'])
@permission_required('employment.manage')
def edit(record_id, link_id):
    person, link = find(record_id, link_id)
    return link_page(person, link)


def link_page(person, link=None):
    form = EmploymentForm(obj=link)
    if request.method == 'GET':
        form.version.data = str(link.version if link else person.version)
    error, status = None, 200
    if form.validate_on_submit():
        try:
            if link:
                update_link(person.id, link.id, form.fecha_ingreso.data, form.version.data, current_user.id)
            else:
                add_link(person.id, form.fecha_ingreso.data, current_user.id, form.solicitud_id.data, form.version.data)
            db.session.commit()
            flash('Vínculo guardado correctamente', 'success')
            return redirect(url_for('employees.detail', record_id=person.id) + '#vinculos-laborales', code=303)
        except StaleDataError:
            db.session.rollback()
            error, status = 'La ficha o el vínculo cambió. Recarga la página antes de guardar.', 409
        except EmploymentConflict as exc:
            db.session.rollback()
            error, status = str(exc), 422
        except SQLAlchemyError:
            db.session.rollback()
            error, status = 'No se pudo guardar el vínculo. La ficha y sus fotografías se conservan.', 503
    elif request.method == 'POST':
        status = 422
    today = paraguay_today()
    calculated = None
    if form.fecha_ingreso.data:
        try:
            validate_entry(person, form.fecha_ingreso.data)
            calculated = seniority(form.fecha_ingreso.data, today)
        except EmploymentConflict:
            pass
    return render_template('employees/employment_form.html', page_title='Editar vínculo' if link else 'Agregar vínculo laboral',
        record=person, link=link, number=link.numero_vinculo if link else next_number(person.id), form=form,
        calculated=calculated, today=today, save_error=error), status


@bp.route('/<int:link_id>/estado', methods=['GET', 'POST'])
@permission_required('employment.manage')
def state(record_id, link_id):
    person, link = find(record_id, link_id)
    form = EmploymentStateForm()
    if request.method == 'GET':
        form.version.data, form.accion.data = str(link.version), 'DESACTIVAR' if link.activo else 'REACTIVAR'
    error, status = None, 200
    if form.validate_on_submit():
        if form.accion.data not in ('DESACTIVAR', 'REACTIVAR') or form.confirmacion.data != 'CONFIRMAR':
            abort(422)
        try:
            change_state(record_id, link_id, form.accion.data == 'REACTIVAR', form.motivo.data, form.version.data, current_user.id)
            db.session.commit()
            flash('Estado del vínculo actualizado correctamente', 'success')
            return redirect(url_for('employees.detail', record_id=record_id) + '#vinculos-laborales', code=303)
        except StaleDataError:
            db.session.rollback()
            error, status = 'El vínculo cambió. Recarga la página antes de confirmar.', 409
        except EmploymentConflict as exc:
            db.session.rollback()
            error, status = str(exc), 409
        except SQLAlchemyError:
            db.session.rollback()
            error, status = 'No se pudo modificar el estado. Los datos anteriores se conservan.', 503
    elif request.method == 'POST':
        status = 422
    return render_template('employees/employment_state.html', page_title='Cambiar estado del vínculo', record=person,
        link=link, form=form, save_error=error), status


@bp.post('/calcular-antiguedad')
@permission_required('employment.manage')
def preview(record_id):
    from datetime import datetime
    person, _ = find(record_id)
    data = request.get_json(silent=True)
    try:
        value = data.get('fecha_ingreso') if isinstance(data, dict) else None
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError()
        entry = datetime.strptime(value, '%d/%m/%Y').date()
        validate_entry(person, entry)
    except (ValueError, TypeError, EmploymentConflict):
        return jsonify(error='Selecciona una fecha completa, no futura y no anterior al nacimiento.'), 422
    today = paraguay_today()
    years, months, days = seniority(entry, today)
    return jsonify(anio_ingreso=entry.year, anios=years, meses=months, dias=days, fecha_consulta=today.strftime('%d/%m/%Y'))
