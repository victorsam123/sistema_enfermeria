from datetime import date, datetime

from flask import Blueprint, jsonify, render_template

from app.dashboard_clock import clock_snapshot
from app.novedades.services import get_novedades_snapshot
from app.security.permissions import can, permission_required

bp = Blueprint('novedades', __name__, url_prefix='/novedades')


def _json_ready(value):
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


@bp.get('/')
@permission_required('novedades.read')
def index():
    snapshot = get_novedades_snapshot(include_photos=can('employees.read'))
    return render_template('novedades/index.html', snapshot=snapshot, clock=clock_snapshot())


@bp.get('/api/resumen')
@permission_required('novedades.read')
def api_resumen():
    return jsonify(_json_ready(get_novedades_snapshot(include_photos=can('employees.read'))))
