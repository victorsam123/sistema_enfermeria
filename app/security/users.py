from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user, fresh_login_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from app.extensions import db
from app.models import Usuario, LogAcceso
from app.models.user_audit import AuditoriaUsuario
from app.models.hospital_services import HistorialAdministrativo
from app.security.permissions import permission_required, manageable_roles, can_manage_account, DENIED
from app.security.user_forms import NewUserForm, UserForm, ResetPasswordForm, AccountStateForm, UserFilters
from app.security.user_operations import create_user, edit_user, reset_password, toggle_account

bp = Blueprint('users', __name__, url_prefix='/usuarios')


@bp.get('/')
@permission_required('users.manage')
def index():
    filters = UserFilters(formdata=request.args, meta={'csrf': False})
    valid = filters.validate()
    query = db.select(Usuario)
    if current_user.rol == 'JEFATURA':
        query = query.where(Usuario.rol.in_(manageable_roles()))
    if valid:
        if filters.q.data:
            query = query.where(db.or_(Usuario.nombre.icontains(filters.q.data, autoescape=True),
                Usuario.username.icontains(filters.q.data, autoescape=True)))
        if filters.rol.data:
            query = query.where(Usuario.rol == filters.rol.data)
        if filters.estado.data:
            query = query.where(Usuario.activo.is_(filters.estado.data == '1'))
    else:
        query = query.where(db.false())
    rows = db.paginate(query.order_by(Usuario.nombre, Usuario.id), page=max(1, request.args.get('page', 1, type=int)), per_page=25, error_out=False)

    def page_url(page):
        return url_for('users.index', page=page, **{k: request.args[k] for k in ('q', 'rol', 'estado') if k in request.args})
    return render_template('users/index.html', page_title='Gestión de Usuarios', filters=filters, rows=rows,
        can_manage_account=can_manage_account, page_url=page_url), 200 if valid else 400


def account_or_403(user_id):
    target = db.get_or_404(Usuario, user_id)
    if not can_manage_account(target):
        abort(403, description=DENIED)
    return target


@bp.route('/nuevo', methods=['GET', 'POST'])
@permission_required('users.manage')
@fresh_login_required
def create():
    return account_form()


@bp.route('/<int:user_id>/editar', methods=['GET', 'POST'])
@permission_required('users.manage')
@fresh_login_required
def edit(user_id):
    return account_form(account_or_403(user_id))


def account_form(target=None):
    form = UserForm(obj=target) if target else NewUserForm()
    if target and request.method == 'GET':
        form.version.data, form.activo.data = str(target.version), '1' if target.activo else '0'
    error, status = None, 200
    # Una promoción enviada a mano se rechaza por autorización, no solo por UI.
    if request.method == 'POST' and request.form.get('rol') not in manageable_roles():
        abort(403, description=DENIED)
    if form.validate_on_submit():
        try:
            if target:
                edit_user(target.id, form)
            else:
                create_user(form)
            flash('Usuario actualizado correctamente.' if target else 'Usuario creado. Debe cambiar la contraseña inicial al ingresar.', 'success')
            return redirect(url_for('users.index'), code=303)
        except IntegrityError:
            db.session.rollback()
            error, status = 'El nombre de usuario ya está registrado. Elige otro.', 409
        except StaleDataError:
            db.session.rollback()
            error, status = 'La cuenta fue modificada. Recarga la página antes de continuar.', 409
        except SQLAlchemyError:
            db.session.rollback()
            error, status = 'No se pudo guardar la cuenta. Vuelve a intentarlo.', 503
    elif request.method == 'POST':
        status = 422
    return render_template('users/form.html', page_title='Editar usuario' if target else 'Agregar nuevo usuario',
        form=form, target=target, save_error=error), status


@bp.route('/<int:user_id>/password', methods=['GET', 'POST'])
@permission_required('users.manage')
@fresh_login_required
def password(user_id):
    target = account_or_403(user_id)
    form = ResetPasswordForm()
    if request.method == 'GET':
        form.version.data = str(target.version)
    if request.method == 'POST' and target.username.casefold() in (form.password.data or '').casefold():
        form.password.errors = ['La contraseña no debe contener el nombre de usuario.']
        return render_template('users/reset_password.html', page_title='Restablecer contraseña', form=form, target=target), 422
    return sensitive_form(target, form, reset_password, 'users/reset_password.html', 'Restablecer contraseña',
        'Contraseña temporal actualizada. Las sesiones anteriores se invalidaron y se exige cambiarla al ingresar.')


@bp.route('/<int:user_id>/estado', methods=['GET', 'POST'])
@permission_required('users.manage')
@fresh_login_required
def state(user_id):
    target = account_or_403(user_id)
    form = AccountStateForm()
    if request.method == 'GET':
        form.version.data = str(target.version)
    return sensitive_form(target, form, toggle_account, 'users/state.html', 'Cambiar estado de cuenta', 'Estado de cuenta actualizado.')


def sensitive_form(target, form, operation, template, title, success):
    error, status = None, 200
    if form.validate_on_submit():
        try:
            operation(target.id, form)
            flash(success, 'success')
            return redirect(url_for('users.index'), code=303)
        except StaleDataError:
            db.session.rollback()
            error, status = 'La cuenta cambió mientras la revisabas. Recarga la página.', 409
        except SQLAlchemyError:
            db.session.rollback()
            error, status = 'No se pudo completar la operación. Vuelve a intentarlo.', 503
    elif request.method == 'POST':
        status = 422
    return render_template(template, page_title=title, target=target, form=form, save_error=error), status


@bp.get('/<int:user_id>/actividad')
@permission_required('users.manage')
def activity(user_id):
    target = db.get_or_404(Usuario, user_id)
    if current_user.rol != 'SUPERADMIN' and not can_manage_account(target):
        abort(403, description=DENIED)
    user_events = db.paginate(db.select(AuditoriaUsuario).where(db.or_(AuditoriaUsuario.usuario_actor_id == user_id,
        AuditoriaUsuario.usuario_afectado_id == user_id)).order_by(AuditoriaUsuario.id.desc()),
        page=max(1, request.args.get('page', 1, type=int)), per_page=30, error_out=False)
    operations = db.paginate(db.select(HistorialAdministrativo).where(HistorialAdministrativo.usuario_id == user_id)
        .order_by(HistorialAdministrativo.id.desc()), page=max(1, request.args.get('operaciones', 1, type=int)), per_page=30, error_out=False)
    access = db.paginate(db.select(LogAcceso).where(LogAcceso.usuario_id == user_id).order_by(LogAcceso.id.desc()),
        page=max(1, request.args.get('accesos', 1, type=int)), per_page=30, error_out=False)
    return render_template('users/activity.html', page_title='Actividad del usuario', target=target,
        user_events=user_events, operations=operations, access=access)
