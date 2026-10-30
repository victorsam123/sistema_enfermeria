from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from app.extensions import db
from app.models import utcnow
from app.models.hospital_services import Servicio
from app.security.permissions import permission_required, can
from app.administration.forms import RecordFilters
from app.hospital_services.classification import apply_service, can_view_diagnosis
from app.hospital_services.forms import ReclassifyForm
from app.hospital_services.records import CATEGORIES, folder_statistics, record_query, matching_details

bp = Blueprint('service_files', __name__, url_prefix='/archivos-por-servicio')


@bp.get('/')
@permission_required('files.read')
def index():
    stats = folder_statistics()
    folders = db.session.execute(db.select(Servicio, stats.c.total, stats.c.ultima).join(
        stats, stats.c.servicio_id == Servicio.id).order_by(Servicio.id)).all()
    return render_template('hospital_services/folders.html', page_title='Archivos por Servicio', folders=folders)


@bp.get('/<int:service_id>/')
@permission_required('files.read')
def folder(service_id):
    service = db.get_or_404(Servicio, service_id)
    counts = {key: db.session.scalar(db.select(db.func.count()).select_from(
        record_query(category, service.id).order_by(None).subquery())) for key, category in CATEGORIES.items()}
    return render_template('hospital_services/folder.html', page_title=service.nombre,
        service=service, categories=CATEGORIES, counts=counts)


@bp.get('/<int:service_id>/<category_key>/')
@permission_required('files.read')
def records(service_id, category_key):
    service = db.get_or_404(Servicio, service_id)
    category = CATEGORIES.get(category_key)
    if not category:
        abort(404)
    if category_key == 'reposos' and not can_view_diagnosis():
        abort(403)
    filters = RecordFilters(formdata=request.args, meta={'csrf': False})
    valid = filters.validate()
    query = record_query(category, service.id, filters.desde.data, filters.hasta.data, filters.q.data)
    if not valid:
        query = query.where(db.false())
    records = db.paginate(query, page=max(1, request.args.get('page', 1, type=int)), per_page=20, error_out=False)

    def page_url(page):
        return url_for('service_files.records', service_id=service.id, category_key=category_key, page=page,
            **{k: request.args[k] for k in ('q', 'desde', 'hasta') if k in request.args})

    return render_template('hospital_services/records.html', page_title=category.label,
        service=service, category=category, category_key=category_key, records=records, filters=filters,
        page_url=page_url, matching_details=matching_details), 200 if valid else 400


@bp.route('/reclasificar/<category_key>/<int:record_id>', methods=['GET', 'POST'])
@permission_required('records.edit')
def reclassify(category_key, record_id):
    category = CATEGORIES.get(category_key)
    if not category:
        abort(404)
    record = db.get_or_404(category.model, record_id)
    if category.kind and record.tipo_cambio != category.kind:
        abort(404)
    if record.eliminado:
        abort(404)
    form = ReclassifyForm()
    status, error = 200, None
    if request.method == 'GET':
        form.servicio_id.data = record.servicio_id
        form.version.data = str(record.version)
    if form.validate_on_submit():
        try:
            if form.version.data != str(record.version):
                raise StaleDataError()
            apply_service(record, form.servicio_id.data, current_user.id)
            record.usuario_modificacion_id = current_user.id
            record.fecha_modificacion = utcnow()
            db.session.commit()
            flash('Servicio corregido. La operación quedó registrada en el historial administrativo.', 'success')
            return redirect(url_for('service_files.records', service_id=record.servicio_id, category_key=category_key), code=303)
        except StaleDataError:
            db.session.rollback()
            status, error = 409, 'El registro fue modificado. Recarga la página antes de reclasificarlo.'
        except SQLAlchemyError:
            db.session.rollback()
            status, error = 503, 'No se pudo cambiar el servicio. No se modificaron los datos.'
    elif request.method == 'POST':
        status = 422
    return render_template('hospital_services/reclassify.html', page_title='Corregir servicio',
        form=form, record=record, category=category, save_error=error), status
