from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from sqlalchemy.orm import selectinload
from app.extensions import db
from app.models.leave_records import Vacacion
from app.models.employees import Funcionario
from app.administration.leave_forms import LeaveFilters, VacacionForm
from app.administration.leave_records import RecordModule, record_page
from app.administration.vacation_roster import build_roster_rows, render_roster_workbook
from app.security.permissions import permission_required
from app.administration.record_access import get_live_record
from app.hospital_services.classification import audit

bp = Blueprint('vacaciones', __name__, url_prefix='/vacaciones')
MODULE = RecordModule(Vacacion, VacacionForm, 'vacaciones',
    'administration/vacaciones.html', 'Vacaciones',
    ('nombres_apellidos', 'fecha_inicio', 'fecha_termino'), 'fecha_inicio',
    'Vacaciones registradas correctamente', 'Vacaciones actualizadas correctamente', vacation=True)


@bp.route('/', methods=['GET', 'POST'])
@permission_required('records.create')
def index():
    return record_page(MODULE)


@bp.route('/<int:record_id>/editar', methods=['GET', 'POST'])
@permission_required('records.edit')
def edit(record_id):
    return record_page(MODULE, get_live_record(Vacacion, record_id))


def planilla_data():
    filters = LeaveFilters(formdata=request.args, meta={'csrf': False})
    if 'orden' not in request.args:
        filters.orden.data = 'asc'
    if not filters.validate() or not filters.desde.data or not filters.hasta.data:
        flash('Selecciona las fechas Desde y Hasta para generar la planilla del período.', 'error')
        args = {key: value for key, value in request.args.items() if key in ('q', 'desde', 'hasta', 'orden')}
        return None, redirect(url_for('vacaciones.index', **args) + '#registros', code=303)

    query = db.select(Vacacion).options(
        selectinload(Vacacion.funcionario).selectinload(Funcionario.vinculos)
    ).where(Vacacion.eliminado.is_(False),
        Vacacion.fecha_termino >= filters.desde.data,
        Vacacion.fecha_inicio <= filters.hasta.data)
    record_id = request.args.get('registro_id')
    if record_id is not None:
        if not record_id.isascii() or not record_id.isdecimal() or len(record_id) > 10:
            flash('El registro de vacaciones solicitado no es válido.', 'error')
            return None, redirect(url_for('vacaciones.index') + '#registros', code=303)
        query = query.where(Vacacion.id == int(record_id))
    if filters.q.data:
        query = query.where(Vacacion.nombres_apellidos.icontains(filters.q.data, autoescape=True))
    order = Vacacion.fecha_inicio.asc() if filters.orden.data == 'asc' else Vacacion.fecha_inicio.desc()
    records = db.session.scalars(query.order_by(order, Vacacion.nombres_apellidos, Vacacion.id)).all()
    rows = build_roster_rows(records, filters.desde.data)
    return (filters, rows, records), None


def planilla_filters():
    result, response = planilla_data()
    if response:
        return None, response
    return result, None


@bp.get('/planilla')
@permission_required('records.print')
def planilla():
    data, response = planilla_filters()
    if response:
        return response
    filters, rows, records = data
    audit('PLANILLA_VACACIONES_IMPRESA', 'vacaciones', details={
        'desde': filters.desde.data.isoformat(), 'hasta': filters.hasta.data.isoformat(),
        'registros': len(records)})
    db.session.commit()
    response = render_template('administration/vacation_roster.html', page_title='Planilla de vacaciones',
        rows=rows, missing_career_count=sum(1 for row in rows if row['cedula'] and not row['career']),
        unlinked_count=sum(1 for row in rows if not row['cedula']))
    response = current_app.make_response(response)
    response.headers['Cache-Control'] = 'no-store, private, max-age=0'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@bp.get('/planilla.xlsx')
@permission_required('records.print')
def planilla_excel():
    data, response = planilla_filters()
    if response:
        return response
    filters, rows, records = data
    output = render_roster_workbook(rows)
    audit('PLANILLA_VACACIONES_DESCARGADA', 'vacaciones', details={
        'desde': filters.desde.data.isoformat(), 'hasta': filters.hasta.data.isoformat(),
        'registros': len(records)})
    db.session.commit()
    response = send_file(output, as_attachment=True, download_name='planilla_vacaciones_2026_2027.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', max_age=0)
    response.headers['Cache-Control'] = 'no-store, private, max-age=0'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response
