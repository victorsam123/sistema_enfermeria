from functools import wraps
from flask import Blueprint, abort, jsonify, render_template
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError
from app.extensions import db
from app.security.permissions import permission_required, can, ROLE_LABELS, DENIED
from app.dashboard_clock import clock_snapshot
from app.dashboard_modules import DASHBOARD_MODULES

bp = Blueprint('main', __name__)


@bp.get('/health')
def health():
    """Disponibilidad sin autenticación ni exposición de datos internos."""
    try:
        db.session.execute(db.text('SELECT 1'))
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(status='unavailable'), 503
    return jsonify(status='ok')


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            accepted = {next((code for code, label in ROLE_LABELS.items() if label == role), role) for role in roles}
            if current_user.rol not in accepted:
                abort(403, description=DENIED)
            return view(*args, **kwargs)
        return wrapped
    return decorator


@bp.get('/')
@permission_required('dashboard')
def dashboard():
    try:
        connected = db.session.execute(db.text('SELECT 1')).scalar() == 1
    except SQLAlchemyError:
        db.session.rollback()
        connected = False
    return render_template('dashboard.html', connected=connected,
                           clock=clock_snapshot(), modules=[m for m in DASHBOARD_MODULES if can(m.permission)])


@bp.get('/api/reloj')
@permission_required('dashboard')
def clock():
    """Sincronización del reloj; no modifica datos ni renueva la sesión."""
    return jsonify(clock_snapshot())
