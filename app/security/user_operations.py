"""Operaciones de cuentas con control de objetivo y bloqueo transaccional."""
from flask import abort
from flask_login import current_user
from sqlalchemy.orm.exc import StaleDataError
from app.extensions import db
from app.models import Usuario
from app.models.user_audit import AuditoriaUsuario
from app.hospital_services.classification import audit
from app.security.permissions import require, can_manage_account, manageable_roles, DENIED


def user_audit(target, action, description, actor_id=None):
    actor_id = current_user.id if actor_id is None else actor_id
    db.session.add(AuditoriaUsuario(usuario_actor_id=actor_id, usuario_afectado_id=target.id,
        accion=action, descripcion=description))
    audit(action, 'usuarios', target.id, details={'descripcion': description}, user_id=actor_id)


def locked_account(user_id, version):
    require('users.manage')
    # populate_existing impide usar una copia anterior tras esperar por el bloqueo.
    target = db.session.scalar(db.select(Usuario).where(Usuario.id == user_id).with_for_update().execution_options(populate_existing=True))
    if target is None:
        abort(404)
    if not can_manage_account(target):
        abort(403, description=DENIED)
    if version != str(target.version):
        raise StaleDataError()
    return target


def create_user(form):
    require('users.manage')
    if form.rol.data not in manageable_roles():
        abort(403, description=DENIED)
    target = Usuario(nombre=form.nombre.data, username=form.username.data, rol=form.rol.data,
        activo=form.activo.data == '1', protegido=False, debe_cambiar_password=True)
    target.set_password(form.password.data)
    db.session.add(target)
    db.session.flush()
    user_audit(target, 'USUARIO_CREADO', f'Cuenta creada con rol {target.rol}; contraseña inicial pendiente de cambio.')
    db.session.commit()
    return target


def edit_user(user_id, form):
    target = locked_account(user_id, form.version.data)
    if form.rol.data not in manageable_roles():
        abort(403, description=DENIED)
    previous_role, previous_state = target.rol, target.activo
    target.nombre, target.username, target.rol = form.nombre.data, form.username.data, form.rol.data
    target.activo = form.activo.data == '1'
    user_audit(target, 'USUARIO_MODIFICADO', 'Datos de identificación de la cuenta actualizados.')
    if previous_role != target.rol:
        user_audit(target, 'ROL_CAMBIADO', f'Rol anterior: {previous_role}. Rol nuevo: {target.rol}.')
    if previous_state != target.activo:
        user_audit(target, 'USUARIO_ACTIVADO' if target.activo else 'USUARIO_DESACTIVADO', 'Estado de la cuenta actualizado.')
    db.session.commit()


def reset_password(user_id, form):
    target = locked_account(user_id, form.version.data)
    target.set_password(form.password.data)
    target.debe_cambiar_password = True
    user_audit(target, 'PASSWORD_RESTABLECIDO', 'Contraseña temporal restablecida; se exige cambiarla en el próximo acceso.')
    db.session.commit()


def toggle_account(user_id, form):
    target = locked_account(user_id, form.version.data)
    if form.confirmacion.data != 'CONFIRMAR':
        abort(400)
    target.activo = not target.activo
    user_audit(target, 'USUARIO_ACTIVADO' if target.activo else 'USUARIO_DESACTIVADO', 'Estado de la cuenta actualizado mediante confirmación.')
    db.session.commit()
