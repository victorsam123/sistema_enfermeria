from flask import Blueprint, render_template, redirect, url_for
from app.security.permissions import permission_required
from app.administration.record_lifecycle import find_record
from app.administration.record_access import get_live_record
from app.hospital_services.records import matching_details
from app.hospital_services.classification import audit
from app.extensions import db

bp = Blueprint('record_print', __name__, url_prefix='/registros')


@bp.get('/<category_key>/<int:record_id>/imprimir')
@permission_required('records.print')
def view(category_key, record_id):
    category, record = find_record(category_key, record_id)
    record = get_live_record(category.model, record_id)
    if category_key == 'vacaciones':
        return redirect(url_for('vacaciones.planilla',
            desde=record.fecha_inicio.strftime('%d/%m/%Y'),
            hasta=record.fecha_termino.strftime('%d/%m/%Y'), registro_id=record.id), code=303)
    audit('IMPRESION_PREPARADA', record.__tablename__, record.id)
    html = render_template('administration/print_record.html', page_title='Documento administrativo',
        category=category, record=record, matching_details=matching_details)
    db.session.commit()
    return html
