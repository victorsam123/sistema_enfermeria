from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, send_file
from flask_login import current_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from app.extensions import db
from app.models import utcnow
from app.models.employees import Funcionario
from app.models.hospital_services import HistorialAdministrativo
from app.documents.service import read_document
from app.documents.storage import DocumentError, StorageError
from app.security.permissions import permission_required
from app.employees.forms import SearchForm, EmployeeForm, EmployeePhotoForm
from app.employees.rules import paraguay_today, completed_age, seniority, normalize_cedula
from app.employees.services import FIELDS, create_employee, locked_employee, update_employee, replace_photo, active_photo
from app.employees.lookup import validate_ticket, consume_lookup
from app.hospital_services.classification import audit

bp = Blueprint('employees', __name__, url_prefix='/funcionarios')


@bp.route('/', methods=['GET', 'POST'])
@permission_required('employees.read')
def search():
    form = SearchForm()
    not_found = False
    valid = form.validate_on_submit()
    if valid:
        record = db.session.scalar(db.select(Funcionario.id).where(Funcionario.cedula == form.cedula.data))
        if record is not None:
            return redirect(url_for('employees.detail', record_id=record), code=303)
        not_found = True
    return render_template('employees/search.html', page_title='BÚSQUEDA DE FUNCIONARIOS',
        form=form, not_found=not_found), 422 if request.method == 'POST' and not valid else 200


@bp.route('/nuevo', methods=['GET', 'POST'])
@permission_required('employees.manage')
def create():
    if request.method == 'POST' and request.form.get('accion') == 'preparar':
        seed = SearchForm()
        if not seed.validate_on_submit():
            abort(422)
        form = EmployeeForm(formdata=None, data={'cedula': seed.cedula.data})
    else:
        form = EmployeeForm()
        if form.validate_on_submit():
            return save_form(form)
    return render_template('employees/form.html', page_title='Registrar funcionario', form=form,
        record=None), 422 if request.method == 'POST' and request.form.get('accion') != 'preparar' else 200


def save_form(form, record=None):
    values = {key: getattr(form, key).data for key in FIELDS}
    error, status = None, 503
    try:
        if record:
            record = locked_employee(record.id, form.version.data)
            update_employee(record, values, form.fotografias.prepared, form.solicitud_id.data, current_user.id)
        else:
            values['fecha_ingreso'] = form.fecha_ingreso.data
            record = create_employee(values, form.fotografias.prepared, form.solicitud_id.data, current_user.id)
        db.session.commit()
        flash('Ficha del funcionario guardada correctamente', 'success')
        return redirect(url_for('employees.detail', record_id=record.id), code=303)
    except IntegrityError:
        db.session.rollback()
        duplicate = db.session.scalar(db.select(Funcionario.id).where(Funcionario.cedula == form.cedula.data))
        error, status = ('Ya existe una ficha con esta cédula. Busca al funcionario antes de registrar otra.', 409) if duplicate else ('No se pudo guardar la ficha. Revisa el servicio y los datos e inténtalo nuevamente.', 422)
    except StaleDataError:
        db.session.rollback()
        error, status = 'Otra operación modificó la ficha. Recarga la página antes de guardar.', 409
    except DocumentError as exc:
        db.session.rollback()
        error, status = str(exc), 503 if isinstance(exc, StorageError) else 422
    except SQLAlchemyError:
        db.session.rollback()
        error = 'No se pudo guardar la ficha. Tus datos permanecen en el formulario; vuelve a seleccionar la fotografía e inténtalo nuevamente.'
    return render_template('employees/form.html', page_title='Editar ficha' if record else 'Registrar funcionario',
        form=form, record=record, save_error=error), status


@bp.get('/<int:record_id>')
@permission_required('employees.read')
def detail(record_id):
    record = db.get_or_404(Funcionario, record_id)
    today = paraguay_today()
    from app.employees.expedient import expediente_counts
    return render_template('employees/detail.html', page_title='FICHA PERSONAL DEL FUNCIONARIO', record=record,
        today=today, age=completed_age(record.fecha_nacimiento, today),
        link_tenures={v.id: seniority(v.fecha_ingreso, today) for v in record.vinculos},
        expediente=expediente_counts(record.id))


@bp.route('/<int:record_id>/editar', methods=['GET', 'POST'])
@permission_required('employees.manage')
def edit(record_id):
    record = db.get_or_404(Funcionario, record_id)
    form = EmployeeForm(obj=record)
    if request.method == 'GET':
        form.version.data = str(record.version)
        # UUID nuevo para una posible sustitución de foto, independiente del alta.
        from uuid import uuid4
        form.solicitud_id.data = str(uuid4())
    if form.validate_on_submit():
        return save_form(form, record)
    return render_template('employees/form.html', page_title='Editar ficha', record=record, form=form), 422 if request.method == 'POST' else 200


@bp.get('/<int:record_id>/fotografia')
@permission_required('employees.read')
def photo(record_id):
    record = db.get_or_404(Funcionario, record_id)
    document = active_photo(record)
    if not document or record.foto_ruta != document.ruta_vista:
        abort(404)
    return send_file(BytesIO(read_document(document)), mimetype='image/jpeg', max_age=0,
        download_name=f'fotografia-{record.id}.jpg')


@bp.route('/<int:record_id>/fotografia/cambiar', methods=['GET', 'POST'])
@permission_required('employees.manage')
def change_photo(record_id):
    record = db.get_or_404(Funcionario, record_id)
    form = EmployeePhotoForm()
    if request.method == 'GET':
        form.version.data = str(record.version)
    error, status = None, 200
    if form.validate_on_submit():
        try:
            if not form.fotografias.prepared:
                raise DocumentError('Selecciona una fotografía personal.')
            record = locked_employee(record_id, form.version.data)
            before = record.foto_ruta
            replace_photo(record, form.fotografias.prepared, form.solicitud_id.data, current_user.id)
            if record.foto_ruta != before:
                record.usuario_modificacion_id, record.fecha_modificacion = current_user.id, utcnow()
            db.session.commit()
            flash('Fotografía actualizada correctamente', 'success')
            return redirect(url_for('employees.detail', record_id=record_id), code=303)
        except StaleDataError:
            db.session.rollback()
            error, status = 'La ficha cambió. Recarga la página antes de reemplazar la fotografía.', 409
        except DocumentError as exc:
            db.session.rollback()
            error, status = str(exc), 503 if isinstance(exc, StorageError) else 422
        except SQLAlchemyError:
            db.session.rollback()
            error, status = 'No se pudo cambiar la fotografía. La anterior se conserva.', 503
    elif request.method == 'POST':
        status = 422
    return render_template('employees/photo.html', page_title='Cambiar fotografía', record=record, form=form, save_error=error), status


@bp.get('/<int:record_id>/historial')
@permission_required('employees.history')
def history(record_id):
    record = db.get_or_404(Funcionario, record_id)
    query = db.select(HistorialAdministrativo).where(HistorialAdministrativo.entidad == 'funcionarios',
        HistorialAdministrativo.registro_id == record.id).order_by(HistorialAdministrativo.fecha_hora.desc(), HistorialAdministrativo.id.desc())
    rows = db.paginate(query, page=max(1, request.args.get('page', 1, type=int)), per_page=30, error_out=False)
    return render_template('employees/history.html', page_title='Historial de la ficha', record=record, rows=rows)


@bp.post('/buscar-para-carga')
@permission_required('employees.lookup')
def operational_lookup():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400)
    validate_ticket(data.get('contexto', ''))
    if not consume_lookup():
        response = jsonify(error='Has realizado demasiadas búsquedas. Inténtalo en un minuto.')
        response.status_code = 429
        response.headers['Retry-After'] = '60'
        return response
    try:
        cedula = normalize_cedula(data.get('cedula'))
    except (ValueError, TypeError, AttributeError) as exc:
        return jsonify(error='Ingresa una cédula válida, con o sin puntos de miles.'), 422
    row = db.session.execute(db.select(Funcionario.id, Funcionario.nombres, Funcionario.apellidos).where(Funcionario.cedula == cedula)).one_or_none()
    if row is None:
        return jsonify(encontrado=False, mensaje='No se encontró ningún funcionario registrado con este número de cédula.')
    return jsonify(encontrado=True, id=row.id, nombre_completo=f'{row.nombres} {row.apellidos}')
