from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, abort, session
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from app.extensions import db
from app.hospital_services.classification import saved_message
from app.models.administration import CambioGuardia, DetalleCambioGuardia
from app.security.permissions import permission_required, can
from app.administration.record_access import get_live_record, loading_confirmation
from app.administration.forms import CambioGuardiaForm, GuardiaDetailForm, RecordFilters
from app.administration.services import SubmissionConflict
from app.administration.guardia_records import create_guardia, update_guardia, detail_values, DetailConflict
from app.administration.guardia_limits import configure_guardia_request
from app.administration.guardia_monthly import GuardiaValidation, monthly_usage, LIMITS
from werkzeug.datastructures import CombinedMultiDict
from app.documents.storage import DocumentError, StorageError

bp = Blueprint('guardias', __name__, url_prefix='/reposo')
bp.record_once(configure_guardia_request)


@bp.get('/cambios-guardia/')
@permission_required('records.create')
def opciones():
    return render_template('administration/guardia_options.html', page_title='Cambio de Guardia')


@bp.route('/cambio-guardia-reemplazante/', methods=['GET', 'POST'])
@permission_required('records.create')
def reemplazante():
    return guardia_page('REEMPLAZO')


@bp.route('/cambio-guardia-emergencia/', methods=['GET', 'POST'])
@permission_required('records.create')
def emergencia():
    return guardia_page('EMERGENCIA')


@bp.route('/cambio-guardia-reemplazante/<int:record_id>/editar', methods=['GET', 'POST'])
@permission_required('records.edit')
def reemplazante_edit(record_id):
    return guardia_page('REEMPLAZO', get_record(record_id, 'REEMPLAZO'))


@bp.route('/cambio-guardia-emergencia/<int:record_id>/editar', methods=['GET', 'POST'])
@permission_required('records.edit')
def emergencia_edit(record_id):
    return guardia_page('EMERGENCIA', get_record(record_id, 'EMERGENCIA'))


@bp.post('/cambios-guardia/control-mensual')
@permission_required('records.create')
def control_mensual():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from flask import jsonify
    from app.employees.lookup import validate_ticket
    from app.models.employees import Funcionario
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        abort(422)
    validate_ticket(data.get('ticket'))
    try:
        day = datetime.strptime(data['fecha'], '%d/%m/%Y').date() if data.get('fecha') else datetime.now(ZoneInfo('America/Asuncion')).date()
        employee_id = int(data['funcionario_id']) if data.get('funcionario_id') else None
    except (ValueError, TypeError, KeyError):
        abort(422)
    name = data.get('nombre', '')
    if not isinstance(name, str) or len(name) > 180:
        abort(422)
    if employee_id:
        name = db.get_or_404(Funcionario, employee_id).nombre_completo
    used = monthly_usage(name, employee_id, day)
    return jsonify(mes=day.strftime('%m/%Y'), usados=used, limites=LIMITS,
        disponibles={k: max(0, LIMITS[k] - used[k]) for k in LIMITS})


@bp.route('/cambio-guardia/', methods=['GET', 'POST'])
@permission_required('records.create')
def normal():
    return guardia_page('NORMAL')


@bp.route('/cambio-guardia-pagada/', methods=['GET', 'POST'])
@permission_required('records.create')
def pagada():
    return guardia_page('PAGADA')


@bp.route('/cambio-guardia/<int:record_id>/editar', methods=['GET', 'POST'])
@permission_required('records.edit')
def normal_edit(record_id):
    return guardia_page('NORMAL', get_record(record_id, 'NORMAL'))


@bp.route('/cambio-guardia-pagada/<int:record_id>/editar', methods=['GET', 'POST'])
@permission_required('records.edit')
def pagada_edit(record_id):
    return guardia_page('PAGADA', get_record(record_id, 'PAGADA'))


def get_record(record_id, category):
    record = get_live_record(CambioGuardia, record_id)
    if record.tipo_cambio != category:
        abort(404)
    return record


def build_form(record, category='NORMAL'):
    if request.method == 'POST':
        data = request.form
        # Compatibilidad con formularios de una fecha abiertos antes de actualizar.
        # Se transforman en las mismas dos filas, sin crear un sistema paralelo.
        if record is None and 'fecha_cambio' in data and not any(k.startswith('detalles-') for k in data):
            data = data.copy()
            for index, role in enumerate(('S', 'R')):
                prefix = f'detalles-{index}-'
                data[prefix + 'participante'] = role
                data[prefix + 'codigo'] = role
                data[prefix + 'fecha_guardia'] = data.get('fecha_cambio', '')
                data[prefix + 'hora_inicio'] = data.get('hora_inicio', '')
                data[prefix + 'hora_fin'] = data.get('hora_fin', '')
        return CambioGuardiaForm(formdata=CombinedMultiDict((request.files, data)))
    if record:
        initial = dict(servicio_id=record.servicio_id, solicitante=record.solicitante, reemplazante=record.reemplazante,
            solicitante_funcionario_id=record.solicitante_funcionario_id or '',
            reemplazante_funcionario_id=record.reemplazante_funcionario_id or '',
            solicitud_id=str(record.solicitud_id), version=str(record.version),
            detalles=[dict(detalle_id=str(d.id), participante=d.participante, fecha_guardia=d.fecha_guardia,
                hora_inicio=d.hora_inicio, hora_fin=d.hora_fin, codigo=d.codigo or '') for d in record.detalles])
    else:
        initial = {'detalles': [{'participante': 'S', 'codigo': 'S'}, {'participante': 'R', 'codigo': 'R'}]}
        if category == 'REEMPLAZO':
            initial['detalles'] = [dict(participante=p, codigo=c) for p, c in [('S', 'L'), ('R', 'G'), ('R', 'L'), ('S', 'G')]]
    return CambioGuardiaForm(formdata=None, data=initial)


def guardia_listing(category, index_endpoint):
    if not can('records.read'):
        return None, None, None, True
    filters = RecordFilters(formdata=request.args, meta={'csrf': False})
    valid = filters.validate()
    query = db.select(CambioGuardia).where(CambioGuardia.tipo_cambio == category, CambioGuardia.eliminado.is_(False))
    if valid:
        if filters.q.data:
            query = query.where(db.or_(CambioGuardia.solicitante.icontains(filters.q.data, autoescape=True),
                                      CambioGuardia.reemplazante.icontains(filters.q.data, autoescape=True)))
        dates = []
        if filters.desde.data:
            dates.append(DetalleCambioGuardia.fecha_guardia >= filters.desde.data)
        if filters.hasta.data:
            dates.append(DetalleCambioGuardia.fecha_guardia <= filters.hasta.data)
        if dates:
            query = query.where(CambioGuardia.detalles.any(db.and_(*dates)))
    else:
        query = query.where(db.false())
    latest = db.select(db.func.max(DetalleCambioGuardia.fecha_guardia)).where(
        DetalleCambioGuardia.cambio_guardia_id == CambioGuardia.id).correlate(CambioGuardia).scalar_subquery()
    records = db.paginate(query.order_by(latest.desc(), CambioGuardia.id.desc()),
        page=max(1, request.args.get('page', 1, type=int)), per_page=20, error_out=False)

    def page_url(number):
        args = {k: request.args[k] for k in ('q', 'desde', 'hasta') if k in request.args}
        return url_for(index_endpoint, page=number, **args)

    return filters, records, page_url, valid


def guardia_page(category, record=None):
    # La categoría se decide por la ruta, nunca por los campos del cliente.
    form = build_form(record, category)
    form._linked_record = record
    key, endpoint, title = {
        'NORMAL': ('guardias', 'normal', 'Cambio de Guardia'),
        'PAGADA': ('pagadas', 'pagada', 'Cambio de Guardia Pagada'),
        'REEMPLAZO': ('reemplazos', 'reemplazante', 'Cambio de Guardia con Reemplazante'),
        'EMERGENCIA': ('emergencias', 'emergencia', 'Cambio de Guardia de Emergencia'),
    }[category]
    index_endpoint, edit_endpoint = 'guardias.' + endpoint, 'guardias.' + endpoint + '_edit'
    error, status = None, 200
    if form.validate_on_submit():
        values = dict(solicitante=form.solicitante.data, reemplazante=form.reemplazante.data, tipo_cambio=category, servicio_id=form.servicio_id.data)
        from app.employees.lookup import record_links
        values.update(record_links(form))
        try:
            if record:
                update_guardia(record, values, detail_values(form), request.form.get('version'), current_user.id)
                flash('Cambio de guardia actualizado correctamente', 'success')
            else:
                created = create_guardia(values, detail_values(form), current_user.id, form.solicitud_id.data)
                if created and category != 'NORMAL':
                    flash('Cambio registrado correctamente. El contador mensual del personal ha sido actualizado.', 'success')
                    from app.administration.guardia_monthly import LABELS
                    day = form.detalles[0].form.fecha_guardia.data
                    summaries = []
                    for role in (('solicitante', 'reemplazante') if category == 'REEMPLAZO' else ('solicitante',)):
                        used = monthly_usage(values[role], values.get(role + '_funcionario_id'), day)
                        summary = ' · '.join(f'{LABELS[k]}: {used[k]} de {LIMITS[k]}, {max(0, LIMITS[k] - used[k])} disponibles' for k in LIMITS)
                        summaries.append(f'CONTROL MENSUAL · {values[role]} · {day:%m/%Y}: {summary}.')
                    session['guardia_monthly_confirmation'] = {'category': category, 'messages': summaries}
                confirmation = loading_confirmation(CambioGuardia, form.solicitud_id.data, index_endpoint)
                if confirmation is not None:
                    return confirmation
                flash(('Cambio de guardia pagada registrado correctamente' if category == 'PAGADA' else 'Cambio de guardia registrado correctamente')
                      if created else 'Este cambio ya fue registrado. No se duplicó la carga.', 'success')
            flash(saved_message(form.servicio_id.data), 'success')
            return redirect(url_for(index_endpoint) + '#registros', code=303)
        except GuardiaValidation as exc:
            db.session.rollback()
            error, status = str(exc), 422
        except DocumentError as exc:
            db.session.rollback()
            error, status = str(exc), 503 if isinstance(exc, StorageError) else 422
        except SubmissionConflict as exc:
            form.solicitud_id.data = str(uuid4())
            error, status = str(exc), 409
        except DetailConflict as exc:
            db.session.rollback()
            error, status = str(exc), 409
        except StaleDataError:
            db.session.rollback()
            error, status = 'Otro envío modificó este cambio. Recarga la edición para conservar todas sus fechas.', 409
        except SQLAlchemyError as exc:
            db.session.rollback()
            current_app.logger.error('Error al guardar cambio de guardia (%s)', type(exc).__name__)
            error, status = 'No se pudo guardar el cambio. Tus datos permanecen en el formulario; vuelve a intentarlo.', 503
    elif request.method == 'POST':
        status = 422
    filters, records, page_url, valid = guardia_listing(category, index_endpoint)
    confirmation = session.get('guardia_monthly_confirmation', {})
    summaries = session.pop('guardia_monthly_confirmation')['messages'] if (
        request.method == 'GET' and confirmation.get('category') == category) else []
    return render_template('administration/guardias.html', page_title=title, category=category,
        form=form, record=record, filters=filters, records=records, page_url=page_url,
        index_endpoint=index_endpoint, edit_endpoint=edit_endpoint, save_error=error,
        category_key=key,
        monthly_confirmation=summaries,
        new_detail_form=GuardiaDetailForm(prefix='detalles-__index__-')), status if valid else 400
