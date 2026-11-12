from uuid import uuid4
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, abort, session, send_file
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from io import BytesIO
import xlsxwriter
from app.extensions import db
from app.hospital_services.classification import saved_message
from app.models import utcnow
from app.models.administration import CambioGuardia, CambioGuardiaCupo, DetalleCambioGuardia
from app.security.permissions import permission_required, can
from app.administration.record_access import get_live_record, loading_confirmation
from app.administration.forms import CambioGuardiaForm, GuardiaDetailForm, RecordFilters
from app.administration.services import SubmissionConflict
from app.administration.guardia_records import create_guardia, update_guardia, detail_values, DetailConflict
from app.administration.guardia_limits import configure_guardia_request
from app.administration.guardia_monthly import (GuardiaValidation, AdvanceConfirmation,
    monthly_usage, monthly_snapshot, lock_monthly, LIMITS, QUOTA_ROLES, next_month)
from werkzeug.datastructures import CombinedMultiDict
from app.documents.storage import DocumentError, StorageError
from wtforms import IntegerField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, NumberRange, Length
from flask_wtf import FlaskForm

bp = Blueprint('guardias', __name__, url_prefix='/reposo')
bp.record_once(configure_guardia_request)


class GuardiaQuotaCorrectionForm(FlaskForm):
    anio = IntegerField('Año de imputación', validators=[DataRequired(), NumberRange(min=1900, max=9999)])
    mes = IntegerField('Mes de imputación', validators=[DataRequired(), NumberRange(min=1, max=12)])
    motivo = TextAreaField('Motivo de corrección', filters=[lambda value: (value or '').strip()],
        validators=[DataRequired(), Length(min=3, max=1000)])
    version = HiddenField(validators=[DataRequired()])


def _quota_report_rows(year, month):
    return db.session.scalars(db.select(CambioGuardiaCupo).join(
        CambioGuardia, CambioGuardia.id == CambioGuardiaCupo.cambio_guardia_id
    ).where(CambioGuardia.eliminado.is_(False),
        CambioGuardiaCupo.anio_imputacion == year,
        CambioGuardiaCupo.mes_imputacion == month
    ).order_by(CambioGuardiaCupo.funcionario_nombre, CambioGuardiaCupo.tipo_cupo,
        CambioGuardiaCupo.fecha_referencia, CambioGuardiaCupo.cambio_guardia_id)).all()


def _quota_report_period():
    from app.dashboard_clock import PARAGUAY_TIMEZONE
    today = datetime.now(PARAGUAY_TIMEZONE).date()
    year_raw, month_raw = request.args.get('anio'), request.args.get('mes')
    if year_raw and (not year_raw.isascii() or not year_raw.isdecimal()):
        abort(400)
    if month_raw and (not month_raw.isascii() or not month_raw.isdecimal()):
        abort(400)
    year, month = int(year_raw) if year_raw else today.year, int(month_raw) if month_raw else today.month
    if not 1900 <= year <= 9999 or not 1 <= month <= 12:
        abort(400)
    return year, month


@bp.get('/cambios-guardia/cupos')
@permission_required('records.edit')
def cupos():
    year, month = _quota_report_period()
    rows = _quota_report_rows(year, month)
    summary = {}
    for allocation in rows:
        key = (allocation.funcionario_id, allocation.funcionario_nombre, allocation.tipo_cupo)
        summary[key] = summary.get(key, 0) + 1
    return render_template('administration/guardia_cupos.html',
        page_title='Control administrativo de cupos de guardia', rows=rows,
        summary=summary, anio=year, mes=month, limits=LIMITS, save_error=None)


@bp.get('/cambios-guardia/cupos.xlsx')
@permission_required('records.edit')
def cupos_excel():
    year, month = _quota_report_period()
    rows = _quota_report_rows(year, month)
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True, 'strings_to_formulas': False,
        'strings_to_urls': False})
    sheet = workbook.add_worksheet('Cupos imputados')
    header = workbook.add_format({'bold': True, 'bg_color': '#17304b', 'font_color': '#ffffff',
        'border': 1})
    headers = ('ID cambio', 'Tipo', 'Funcionario', 'Participante', 'Fecha real del cambio',
        'Fecha de referencia', 'Mes de imputación', 'Uso anticipado', 'Cupo permitido',
        'Usuario de registro', 'Fecha de registro')
    sheet.write_row(0, 0, headers, header)
    for index, allocation in enumerate(rows, start=1):
        sheet.write_row(index, 0, (
            allocation.cambio_guardia_id,
            allocation.tipo_cupo,
            allocation.funcionario_nombre,
            'Solicitante' if allocation.participante == 'S' else 'Reemplazante',
            allocation.cambio.fecha_cambio.strftime('%d/%m/%Y'),
            allocation.fecha_referencia.strftime('%d/%m/%Y'),
            f'{allocation.mes_imputacion:02d}/{allocation.anio_imputacion}',
            'Sí' if allocation.uso_anticipado else 'No',
            LIMITS[allocation.tipo_cupo],
            allocation.usuario_registro.username,
            allocation.fecha_creacion.strftime('%d/%m/%Y %H:%M') if allocation.fecha_creacion else '',
        ))
    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, max(1, len(rows)), len(headers) - 1)
    for column, width in enumerate((12, 16, 28, 16, 18, 18, 18, 15, 16, 24, 21)):
        sheet.set_column(column, column, width)
    workbook.close()
    output.seek(0)
    return send_file(output, as_attachment=True,
        download_name=f'control_cupos_guardia_{year}_{month:02d}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', max_age=0)


@bp.post('/cambios-guardia/cupos/<int:allocation_id>/corregir')
@permission_required('records.edit')
def corregir_cupo(allocation_id):
    form = GuardiaQuotaCorrectionForm()
    if not form.validate_on_submit():
        flash('Completa un mes, año y motivo válidos para corregir el cupo.', 'error')
        return redirect(url_for('guardias.cupos'), code=303)
    try:
        lock_monthly()
        allocation = db.session.scalar(db.select(CambioGuardiaCupo).where(
            CambioGuardiaCupo.id == allocation_id).with_for_update())
        if not allocation:
            abort(404)
        record = db.session.scalar(db.select(CambioGuardia).where(
            CambioGuardia.id == allocation.cambio_guardia_id).with_for_update())
        if not record or record.eliminado:
            abort(404)
        if form.version.data != str(allocation.version):
            raise StaleDataError()

        reference_period = date(allocation.fecha_referencia.year, allocation.fecha_referencia.month, 1)
        allowed_periods = {reference_period}
        if allocation.fecha_referencia.day >= 16:
            allowed_periods.add(next_month(reference_period))
        target = date(form.anio.data, form.mes.data, 1)
        if target not in allowed_periods:
            flash('La imputación debe corresponder al mes de referencia o, desde el día 16, al mes siguiente.', 'error')
            return redirect(url_for('guardias.cupos', anio=target.year, mes=target.month), code=303)
        if (target.year, target.month) != (allocation.anio_imputacion, allocation.mes_imputacion):
            used = monthly_usage(allocation.funcionario_nombre, allocation.funcionario_id,
                target, exclude=record.id)[allocation.tipo_cupo]
            if used >= LIMITS[allocation.tipo_cupo]:
                flash('No hay cupo disponible en el mes seleccionado. No se modificó la imputación.', 'error')
                return redirect(url_for('guardias.cupos', anio=target.year, mes=target.month), code=303)

        previous = {'anio_imputacion': allocation.anio_imputacion,
            'mes_imputacion': allocation.mes_imputacion, 'uso_anticipado': allocation.uso_anticipado}
        anticipated_period = next_month(reference_period)
        allocation.anio_imputacion, allocation.mes_imputacion = target.year, target.month
        allocation.uso_anticipado = (target == anticipated_period and allocation.fecha_referencia.day >= 16)
        allocation.usuario_modificacion_id = current_user.id
        allocation.fecha_modificacion = utcnow()
        from app.hospital_services.classification import audit
        audit('CUPO_GUARDIA_CORREGIDO', 'cupos_cambios_guardia', allocation.id,
            details={'anterior': previous, 'nuevo': {
                'anio_imputacion': allocation.anio_imputacion,
                'mes_imputacion': allocation.mes_imputacion,
                'uso_anticipado': allocation.uso_anticipado,
            }, 'motivo': form.motivo.data}, user_id=current_user.id)
        db.session.commit()
        flash('Imputación corregida y auditada correctamente.', 'success')
        return redirect(url_for('guardias.cupos', anio=target.year, mes=target.month), code=303)
    except StaleDataError:
        db.session.rollback()
        flash('Otro usuario modificó este cupo. Recarga la página.', 'error')
        return redirect(url_for('guardias.cupos'), code=303)
    except SQLAlchemyError as exc:
        db.session.rollback()
        current_app.logger.error('Error al corregir imputación de cupo (%s)', type(exc).__name__)
        flash('No se pudo corregir el cupo. No se modificaron los datos.', 'error')
        return redirect(url_for('guardias.cupos'), code=303)


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
    kind = data.get('tipo_cambio')
    if kind not in QUOTA_ROLES:
        abort(422)
    record_id = data.get('record_id')
    if record_id is not None and (not str(record_id).isascii() or not str(record_id).isdecimal()):
        abort(422)
    exclude = int(record_id) if record_id else None
    if exclude is not None:
        if not can('records.edit'):
            abort(403)
        record = db.session.get(CambioGuardia, exclude)
        if not record or record.eliminado or record.tipo_cambio != kind:
            abort(404)
    snapshot = monthly_snapshot(name, employee_id, day, exclude=exclude)
    used = snapshot['usados'][kind]
    available = snapshot['disponibles'][kind]
    next_available = snapshot['disponibles_mes_siguiente'][kind]
    needs_advance = not available and day.day >= 16 and next_available > 0
    can_save = bool(available or needs_advance)
    snapshot.update(requiere_anticipacion=needs_advance, puede_guardar=can_save,
        tipo_cambio=kind, usados_tipo=used, disponibles_tipo=available,
        disponibles_siguiente_tipo=next_available)
    return jsonify(snapshot)


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
    requires_advance_confirmation, advance_confirmation_message = False, None
    if form.validate_on_submit():
        values = dict(solicitante=form.solicitante.data, reemplazante=form.reemplazante.data, tipo_cambio=category, servicio_id=form.servicio_id.data)
        from app.employees.lookup import record_links
        values.update(record_links(form))
        try:
            if record:
                update_guardia(record, values, detail_values(form), request.form.get('version'), current_user.id,
                    confirmed_advance=request.form.get('confirmar_cupo_anticipado') == '1')
                flash('Cambio de guardia actualizado correctamente', 'success')
            else:
                created = create_guardia(values, detail_values(form), current_user.id, form.solicitud_id.data,
                    confirmed_advance=request.form.get('confirmar_cupo_anticipado') == '1')
                if created and category != 'NORMAL':
                    flash('Cambio registrado correctamente. El contador mensual del personal ha sido actualizado.', 'success')
                    from app.administration.guardia_monthly import LABELS
                    summaries = []
                    saved_record = db.session.scalar(db.select(CambioGuardia).where(
                        CambioGuardia.solicitud_id == form.solicitud_id.data))
                    allocations = db.session.scalars(db.select(CambioGuardiaCupo).where(
                        CambioGuardiaCupo.cambio_guardia_id == saved_record.id))
                    for allocation in allocations:
                        assigned_period = allocation.fecha_referencia.replace(
                            year=allocation.anio_imputacion, month=allocation.mes_imputacion)
                        used = monthly_usage(allocation.funcionario_nombre, allocation.funcionario_id, assigned_period)
                        summary = (f'{allocation.tipo_cupo} {used[allocation.tipo_cupo]} de '
                            f'{LIMITS[allocation.tipo_cupo]}, '
                            f'{max(0, LIMITS[allocation.tipo_cupo] - used[allocation.tipo_cupo])} disponibles')
                        mode = ' · cupo anticipado' if allocation.uso_anticipado else ''
                        summaries.append(f'CONTROL DE CUPOS · {allocation.funcionario_nombre} · '
                            f'{allocation.mes_imputacion:02d}/{allocation.anio_imputacion}: {summary}{mode}.')
                    session['guardia_monthly_confirmation'] = {'category': category, 'messages': summaries}
                confirmation = loading_confirmation(CambioGuardia, form.solicitud_id.data, index_endpoint)
                if confirmation is not None:
                    return confirmation
                flash(('Cambio de guardia pagada registrado correctamente' if category == 'PAGADA' else 'Cambio de guardia registrado correctamente')
                      if created else 'Este cambio ya fue registrado. No se duplicó la carga.', 'success')
            flash(saved_message(form.servicio_id.data), 'success')
            return redirect(url_for(index_endpoint) + '#registros', code=303)
        except AdvanceConfirmation as exc:
            db.session.rollback()
            requires_advance_confirmation, advance_confirmation_message = True, str(exc)
            error, status = str(exc), 409
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
        requires_advance_confirmation=requires_advance_confirmation,
        advance_confirmation_message=advance_confirmation_message,
        new_detail_form=GuardiaDetailForm(prefix='detalles-__index__-')), status if valid else 400
