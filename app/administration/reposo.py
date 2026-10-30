from flask import Blueprint
from app.extensions import db
from app.models.reposos import Reposo
from app.administration.reposos.views import reposo_page
from app.security.permissions import permission_required, can
from app.administration.record_access import get_live_record, loading_confirmation

bp = Blueprint('reposo', __name__, url_prefix='/reposo')


@bp.route('/', methods=['GET', 'POST'])
@permission_required('records.create')
def index():
    return reposo_page()


@bp.route('/<int:record_id>/editar', methods=['GET', 'POST'])
@permission_required('records.edit')
def edit(record_id):
    return reposo_page(get_live_record(Reposo, record_id))
