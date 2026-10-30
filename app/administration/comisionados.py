from flask import Blueprint
from app.extensions import db
from app.models.leave_records import Comisionado
from app.administration.leave_forms import ComisionadoForm
from app.administration.leave_records import RecordModule, record_page
from app.security.permissions import permission_required, can
from app.administration.record_access import get_live_record, loading_confirmation

bp = Blueprint('comisionados', __name__, url_prefix='/comisionados')
MODULE = RecordModule(Comisionado, ComisionadoForm, 'comisionados',
    'administration/comisionados.html', 'Comisionados',
    ('nombres_apellidos', 'fecha_inasistencia', 'motivo', 'lugar'), 'fecha_inasistencia',
    'Comisionado registrado correctamente', 'Comisionado actualizado correctamente')


@bp.route('/', methods=['GET', 'POST'])
@permission_required('records.create')
def index():
    return record_page(MODULE)


@bp.route('/<int:record_id>/editar', methods=['GET', 'POST'])
@permission_required('records.edit')
def edit(record_id):
    return record_page(MODULE, get_live_record(Comisionado, record_id))
