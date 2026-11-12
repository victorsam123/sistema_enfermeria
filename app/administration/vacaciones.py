from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from sqlalchemy.orm import selectinload
from app.extensions import db
from app.models.leave_records import Vacacion
from app.models.employees import Funcionario
from app.models.hospital_services import Servicio
from wtforms import SelectField
from app.administration.leave_forms import LeaveFilters, VacacionForm
from app.administration.leave_records import RecordModule, record_page
from app.administration.vacation_roster import build_roster_rows, render_roster_workbook
from app.security.permissions import permission_required
from app.administration.record_access import get_live_record
from app.hospital_services.classification import audit
from app.administration.office_documents import convert_to_pdf, private_download, OfficeConversionError

bp = Blueprint('vacaciones', __name__, url_prefix='/vacaciones')
MODULE = RecordModule(Vacacion, VacacionForm, 'vacaciones',
    'administration/vacaciones.html', 'Vacaciones',
    ('nombres_apellidos', 'fecha_inicio', 'fecha_termino'), 'fecha_inicio',
    'Vacaciones registradas correctamente', 'Vacaciones actualizadas correctamente', vacation=True)


class RosterPrintFilters(LeaveFilters):
    servicio = SelectField('Servicio hospitalario', coerce=int, default=0, choices=[])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.servicio.choices = [(0, 'Selecciona un servicio para generar la planilla')] + [
            (s.id, s.nombre) for s in db.session.scalars(db.select(Servicio).order_by(Servicio.nombre))]


@bp.route('/', methods=['GET', 'POST'])
@permission_required('records.create')
def index():
    return record_page(MODULE)


@bp.route('/<int:record_id>/editar', methods=['GET', 'POST'])
@permission_required('records.edit')
def edit(record_id):
    return record_page(MODULE, get_live_record(Vacacion, record_id))


def planilla_data():
    filters = RosterPrintFilters(formdata=request.args, meta={'csrf': False})
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
    if filters.servicio.data:
        query = query.where(Vacacion.servicio_id == filters.servicio.data)
    if request.args.get('seleccion') == '1':
        selected = request.args.getlist('registros')
        valid_ids = all(v.isascii() and v.isdecimal() and 0 < len(v) <= 10 for v in selected)
        ids = [int(v) for v in selected] if valid_ids else []
        if not ids or len(ids) != len(set(ids)):
            flash('Selecciona registros distintos para la planilla; no se agregó ningún duplicado.', 'error')
            return None, redirect(url_for('vacaciones.planilla', **{k: v for k, v in request.args.items()
                if k not in ('seleccion', 'registros')}), code=303)
        query = query.where(Vacacion.id.in_(ids))
    order = Vacacion.fecha_inicio.asc() if filters.orden.data == 'asc' else Vacacion.fecha_inicio.desc()
    records = db.session.scalars(query.order_by(order, Vacacion.nombres_apellidos, Vacacion.id)).all()
    if request.args.get('seleccion') == '1' and {r.id for r in records} != set(ids):
        flash('La selección contiene registros fuera del período o servicio indicado. Revisa la selección antes de generar.', 'error')
        return None, redirect(url_for('vacaciones.planilla', **{k: v for k, v in request.args.items()
            if k not in ('seleccion', 'registros')}), code=303)
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
    response = render_template('administration/vacation_roster.html', page_title='Preparar planilla oficial de vacaciones',
        filters=filters, records=records,
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
    services = {r.servicio_id for r in records}
    if len(services) > 1:
        flash('Selecciona un solo servicio para generar su planilla oficial sin mezclar personal de otras áreas.', 'error')
        return redirect(url_for('vacaciones.planilla', **request.args.to_dict()), code=303)
    output = render_roster_workbook(rows, service_name=records[0].servicio.nombre if records else None)
    audit('PLANILLA_VACACIONES_DESCARGADA', 'vacaciones', details={
        'desde': filters.desde.data.isoformat(), 'hasta': filters.hasta.data.isoformat(),
        'registros': len(records)})
    db.session.commit()
    response = send_file(output, as_attachment=True, download_name='planilla_vacaciones_2026_2027.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', max_age=0)
    response.headers['Cache-Control'] = 'no-store, private, max-age=0'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@bp.get('/planilla.pdf')
@permission_required('records.print')
def planilla_pdf():
    data, response = planilla_filters()
    if response:
        return response
    filters, rows, records = data
    if len({r.servicio_id for r in records}) > 1:
        flash('Selecciona un solo servicio para generar su planilla oficial.', 'error')
        return redirect(url_for('vacaciones.planilla', **request.args.to_dict()), code=303)
    try:
        workbook = render_roster_workbook(rows, service_name=records[0].servicio.nombre if records else None).getvalue()
        pdf = convert_to_pdf(workbook, '.xlsx')
    except OfficeConversionError as exc:
        db.session.rollback()
        flash(str(exc), 'error')
        return redirect(url_for('vacaciones.planilla', **request.args.to_dict()), code=303)
    audit('PLANILLA_VACACIONES_PDF', 'vacaciones', details={'registros': [r.id for r in records],
        'desde': filters.desde.data.isoformat(), 'hasta': filters.hasta.data.isoformat()})
    db.session.commit()
    return private_download(pdf, 'planilla_vacaciones_2026_2027.pdf', 'application/pdf',
        attachment=request.args.get('descargar') == '1')
