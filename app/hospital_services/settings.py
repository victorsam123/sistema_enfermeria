from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from app.extensions import db
from app.models.hospital_services import Servicio, HistorialAdministrativo, PENDING_CODE
from app.security.permissions import permission_required, can
from app.hospital_services.forms import ServiceForm
from app.hospital_services.classification import audit

bp = Blueprint('service_settings', __name__, url_prefix='/configuracion/servicios')


@bp.route('/', methods=['GET', 'POST'])
@permission_required('services.manage')
def index():
    return service_page()


@bp.route('/<int:service_id>/editar', methods=['GET', 'POST'])
@permission_required('services.manage')
def edit(service_id):
    service = db.get_or_404(Servicio, service_id)
    if service.codigo == PENDING_CODE:
        abort(403)
    return service_page(service)


def service_page(service=None):
    editing = service is not None
    form = ServiceForm(obj=service)
    status, error = 200, None
    if service and request.method == 'GET':
        form.version.data = str(service.version)
    if form.validate_on_submit():
        try:
            if service:
                if form.version.data != str(service.version):
                    raise StaleDataError()
                if form.codigo.data != service.codigo:
                    form.codigo.errors.append('El código es permanente. Puedes modificar el nombre.')
                    status = 422
                else:
                    audit('SERVICIO_MODIFICADO', 'servicios', service.id, details={
                        'nombre_anterior': service.nombre, 'nombre_nuevo': form.nombre.data,
                        'activo_anterior': service.activo, 'activo_nuevo': form.activo.data})
                    service.nombre, service.activo = form.nombre.data, form.activo.data
            else:
                if form.codigo.data == PENDING_CODE:
                    form.codigo.errors.append('Código reservado.')
                    status = 422
                else:
                    service = Servicio(nombre=form.nombre.data, codigo=form.codigo.data, activo=form.activo.data)
                    db.session.add(service)
                    db.session.flush()
                    audit('SERVICIO_CREADO', 'servicios', service.id, details={'nombre': service.nombre, 'codigo': service.codigo})
            if status == 200:
                db.session.commit()
                flash('Catálogo de servicios actualizado correctamente.', 'success')
                return redirect(url_for('service_settings.index'), code=303)
        except IntegrityError:
            db.session.rollback()
            status, error = 409, 'El código ya está registrado. Utiliza otro código o edita el servicio existente.'
        except StaleDataError:
            db.session.rollback()
            status, error = 409, 'El servicio fue modificado. Recarga la página para revisar sus datos.'
        except SQLAlchemyError:
            db.session.rollback()
            status, error = 503, 'No se pudo actualizar el catálogo. No se modificaron los datos.'
    elif request.method == 'POST':
        status = 422
    services = db.session.scalars(db.select(Servicio).order_by(Servicio.id)).all()
    return render_template('hospital_services/settings.html', page_title='Configuración de servicios',
        form=form, service=service if editing else None, services=services, save_error=error), status


@bp.get('/historial')
@permission_required('activity.read')
def history():
    from flask_login import current_user
    from app.models import Usuario
    query = db.select(HistorialAdministrativo)
    if current_user.rol == 'JEFATURA':
        managed = db.select(Usuario.id).where(Usuario.rol.in_(('OPERADOR', 'SUPERVISOR')))
        query = query.where(db.or_(HistorialAdministrativo.entidad != 'usuarios', HistorialAdministrativo.registro_id.in_(managed)))
    rows = db.paginate(query.order_by(HistorialAdministrativo.id.desc()),
        page=max(1, request.args.get('page', 1, type=int)), per_page=30, error_out=False)
    return render_template('hospital_services/history.html', page_title='Historial administrativo', rows=rows)
