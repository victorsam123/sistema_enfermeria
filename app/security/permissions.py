from functools import wraps
from flask import abort
from flask_login import current_user, login_required

ROLE_LABELS = {'SUPERADMIN': 'Superadministrador', 'JEFATURA': 'Jefatura de Enfermería',
               'OPERADOR': 'Operador', 'SUPERVISOR': 'Supervisor'}
LOAD = frozenset({'dashboard', 'records.create', 'documents.create', 'employees.lookup'})
ADMIN = LOAD | {'records.read', 'records.edit', 'records.delete', 'records.print',
    'reports.export', 'files.read', 'diagnoses.read', 'users.manage', 'activity.read',
    'documents.read', 'documents.download', 'documents.manage', 'documents.history',
    'employees.read', 'employees.manage', 'employees.history', 'employment.read', 'employment.manage', 'employment.history'}
PERMISSIONS = {'SUPERADMIN': ADMIN | {'records.restore', 'services.manage', 'configuration'},
               'JEFATURA': ADMIN, 'OPERADOR': LOAD, 'SUPERVISOR': LOAD}
DENIED = 'No tiene permisos para realizar esta operación'


def can(permission, user=None):
    user = current_user if user is None else user
    return bool(user.is_authenticated and user.activo and permission in PERMISSIONS.get(user.rol, ()))


def require(permission):
    if not can(permission):
        abort(403, description=DENIED)


def permission_required(permission):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            require(permission)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def manageable_roles(actor=None):
    actor = current_user if actor is None else actor
    return tuple(ROLE_LABELS) if actor.rol == 'SUPERADMIN' else ('OPERADOR', 'SUPERVISOR') if actor.rol == 'JEFATURA' else ()


def can_manage_account(target, actor=None):
    actor = current_user if actor is None else actor
    return can('users.manage', actor) and not target.protegido and target.username != 'victor' and target.rol in manageable_roles(actor)
