"""Selección, revisión, generación y archivo privado de notas oficiales."""
from hashlib import sha256
from pathlib import Path
import re
from uuid import UUID
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.administration import Justificativo
from app.models.employees import Funcionario
from app.models.issued_notes import NotaCompensatoria
from app.security.permissions import permission_required
from app.administration.forms import name_key
from app.administration.compensatory_forms import PrintFilters, NoteSelectionForm, NotePrintForm, date_list
from app.administration.compensatory_document import excluded_reason, positive_reason, render_compensatory_note
from app.administration.office_documents import convert_to_pdf, private_download, OfficeConversionError
from app.employees.rules import paraguay_today
from app.hospital_services.classification import audit

bp = Blueprint('compensatory_notes', __name__, url_prefix='/justificativos/notas-compensatorias')
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


@bp.record_once
def printing_request_limit(state):
    base = state.app.request_class

    class PrintingRequest(base):
        @property
        def max_content_length(self):
            if self.blueprint == 'compensatory_notes' and self.method == 'POST':
                return 2 * 1024 * 1024
            return super().max_content_length

    state.app.request_class = PrintingRequest


def live_records(ids, locked=False):
    if not ids or len(ids) > 200 or len(ids) != len(set(ids)):
        raise ValueError('Selecciona entre 1 y 200 justificativos distintos.')
    query = db.select(Justificativo).where(Justificativo.id.in_(ids), Justificativo.eliminado.is_(False))
    if locked:
        query = query.with_for_update(of=Justificativo).execution_options(populate_existing=True)
    records = db.session.scalars(query).all()
    if len(records) != len(ids) or any(excluded_reason(r.motivo) for r in records):
        raise ValueError('La selección contiene registros no disponibles o motivos excluidos: capacitación, llegada tardía o falta de marcación de entrada.')
    found = {r.id: r for r in records}
    return [found[i] for i in ids]


def employee_choices(form):
    choices = [(0, 'Selecciona la ficha por nombre y cédula; no se asigna por coincidencia de nombres')] + [
        (p.id, f'{p.nombre_completo} · C.I. {p.cedula}') for p in db.session.scalars(
            db.select(Funcionario).order_by(Funcionario.apellidos, Funcionario.nombres))]
    for entry in form.filas:
        entry.form.funcionario_id.choices = choices


def printable_rows(form, records):
    rows = []
    for entry, record in zip(form.filas, records):
        f = entry.form
        if f.version.data != str(record.version):
            raise ValueError(f'El justificativo #{record.id} cambió. Vuelve a seleccionarlo para revisar sus datos actuales.')
        person = db.session.get(Funcionario, f.funcionario_id.data)
        if not person:
            raise ValueError(f'Selecciona la ficha de la persona del justificativo #{record.id}.')
        if record.funcionario_id:
            if person.id != record.funcionario_id:
                raise ValueError(f'La cédula seleccionada no pertenece a la ficha vinculada al justificativo #{record.id}.')
        elif name_key(person.nombre_completo) != name_key(record.nombres_apellidos):
            raise ValueError(f'El nombre de la ficha seleccionada no coincide con el justificativo #{record.id}. No se asignan cédulas por semejanza.')
        worked, free = date_list(f.fecha_realizacion.data), date_list(f.fecha_libre.data)
        if record.fecha_cobertura and record.fecha_cobertura not in worked:
            raise ValueError(f'Conserva la fecha de cobertura del justificativo #{record.id} entre las fechas efectivamente trabajadas.')
        if record.fecha_inasistencia not in free:
            raise ValueError(f'Conserva la fecha de inasistencia del justificativo #{record.id} entre los días libres.')
        rows.append(dict(record_id=record.id, employee_id=person.id, record_version=record.version,
            name=record.nombres_apellidos, cedula=person.cedula, service=record.servicio.nombre,
            worked_dates=', '.join(d.strftime('%d/%m/%Y') for d in worked),
            free_dates=', '.join(d.strftime('%d/%m/%Y') for d in free),
            worked_hours=re.sub(r'\s*(?:a|A|-)\s*', ' a ', f.horario_cumplido.data.strip()),
            free_hours=re.sub(r'\s*(?:a|A|-)\s*', ' a ', f.horario_libre.data.strip())))
    return rows


@bp.route('/', methods=['GET', 'POST'])
@permission_required('records.print')
def prepare():
    error, status, records = None, 200, []
    action = request.form.get('accion')
    if request.method == 'POST' and action != 'preparar':
        form = NotePrintForm()
        employee_choices(form)
        if form.validate_on_submit():
            try:
                ids = [int(entry.form.justificativo_id.data) for entry in form.filas]
                records = live_records(ids, locked=action == 'emitir')
                rows = printable_rows(form, records)
                if action not in ('vista', 'word', 'pdf', 'emitir'):
                    abort(400)
                word = render_compensatory_note(rows, form.numero.data, form.fecha_emision.data)
                name = f'nota_{form.numero.data}_{form.fecha_emision.data.year}'
                if action == 'word':
                    return private_download(word, name + '.docx', DOCX_MIME)
                if action == 'emitir':
                    existing = db.session.scalar(db.select(NotaCompensatoria).where(
                        NotaCompensatoria.solicitud_id == UUID(form.solicitud_id.data)))
                    if existing:
                        if existing.usuario_id != current_user.id or existing.documento_sha256 != sha256(word).hexdigest():
                            raise ValueError('Este envío ya fue utilizado con otros datos. Prepara otra nota.')
                        return redirect(url_for('compensatory_notes.issued', note_id=existing.id), code=303)
                    if db.session.scalar(db.select(NotaCompensatoria.id).where(
                            NotaCompensatoria.anio == form.fecha_emision.data.year, NotaCompensatoria.numero == form.numero.data)):
                        raise ValueError('Ese número de nota ya fue emitido durante el mismo año. Utiliza otro número.')
                pdf = convert_to_pdf(word, '.docx')
                if action != 'emitir':
                    return private_download(pdf, name + '.pdf', 'application/pdf', attachment=action == 'pdf')
                note = NotaCompensatoria(numero=form.numero.data, anio=form.fecha_emision.data.year,
                    fecha_emision=form.fecha_emision.data, solicitud_id=UUID(form.solicitud_id.data), usuario_id=current_user.id,
                    registros=[{'justificativo_id': r['record_id'], 'funcionario_id': r['employee_id'],
                        'version_justificativo': r['record_version'], 'datos_impresos': {
                            k: v for k, v in r.items() if k not in ('record_id', 'employee_id', 'record_version')}} for r in rows],
                    plantilla_sha256=sha256((Path(current_app.root_path) / 'assets/nota_dia_compensatorio.docx').read_bytes()).hexdigest(),
                    documento_sha256=sha256(word).hexdigest(), pdf_sha256=sha256(pdf).hexdigest(), documento=word, pdf=pdf)
                db.session.add(note)
                db.session.flush()
                audit('NOTA_COMPENSATORIA_EMITIDA', 'notas_compensatorias', note.id,
                    details={'numero': note.numero, 'anio': note.anio, 'registros': ids, 'version': note.version})
                db.session.commit()
                flash('Nota emitida y archivada. El número quedó reservado para este año; los justificativos originales no se modificaron.', 'success')
                return redirect(url_for('compensatory_notes.issued', note_id=note.id), code=303)
            except OfficeConversionError as exc:
                db.session.rollback()
                error, status = str(exc), 503
            except IntegrityError:
                db.session.rollback()
                error, status = 'El número de nota o el envío acaba de ser utilizado. Consulta las notas emitidas; no se duplicó la operación.', 409
            except (ValueError, TypeError) as exc:
                db.session.rollback()
                error, status = str(exc), 422
        else:
            status = 422
        # Recuperar el contexto para que los errores no borren la preparación.
        if not records:
            try:
                records = live_records([int(e.form.justificativo_id.data) for e in form.filas])
            except (ValueError, TypeError):
                records = []
        return render_template('administration/compensatory_prepare.html', page_title='Preparar nota de día compensatorio',
            form=form, records=records, save_error=error), status

    selection = NoteSelectionForm()
    if selection.validate_on_submit():
        try:
            records = live_records(selection.registros.data)
            form = NotePrintForm(formdata=None, data={'fecha_emision': paraguay_today(), 'filas': [dict(
                justificativo_id=str(r.id), version=str(r.version), funcionario_id=r.funcionario_id or 0,
                fecha_realizacion=r.fecha_cobertura.strftime('%d/%m/%Y') if r.fecha_cobertura else '',
                fecha_libre=r.fecha_inasistencia.strftime('%d/%m/%Y')) for r in records]})
            employee_choices(form)
            return render_template('administration/compensatory_prepare.html', page_title='Preparar nota de día compensatorio', form=form, records=records)
        except ValueError as exc:
            error, status = str(exc), 422
    elif request.method == 'POST':
        status = 422
    filters = PrintFilters(formdata=request.args, meta={'csrf': False})
    query = db.select(Justificativo).where(Justificativo.eliminado.is_(False))
    if filters.validate():
        if filters.q.data:
            query = query.where(Justificativo.nombres_apellidos.icontains(filters.q.data, autoescape=True))
        if filters.desde.data:
            query = query.where(Justificativo.fecha_inasistencia >= filters.desde.data)
        if filters.hasta.data:
            query = query.where(Justificativo.fecha_inasistencia <= filters.hasta.data)
        if filters.servicio.data:
            query = query.where(Justificativo.servicio_id == filters.servicio.data)
    else:
        query = query.where(db.false())
        status = 422
    candidates = [r for r in db.session.scalars(query.order_by(Justificativo.fecha_inasistencia, Justificativo.id)) if not excluded_reason(r.motivo)]
    notes = db.paginate(db.select(NotaCompensatoria).order_by(NotaCompensatoria.id.desc()),
        page=max(1, request.args.get('pagina_notas', 1, type=int) or 1), per_page=30, error_out=False)
    return render_template('administration/compensatory_select.html', page_title='Generar nota de día compensatorio',
        filters=filters, selection=selection, records=candidates, notes=notes, positive_reason=positive_reason,
        initial_id=request.args.get('registro_id', type=int), save_error=error), status


@bp.get('/<int:note_id>')
@permission_required('records.print')
def issued(note_id):
    note = db.get_or_404(NotaCompensatoria, note_id)
    return render_template('administration/compensatory_issued.html', page_title='Nota de día compensatorio emitida', note=note)


@bp.get('/<int:note_id>/<format>')
@permission_required('records.print')
def download(note_id, format):
    note = db.get_or_404(NotaCompensatoria, note_id)
    if format not in ('word', 'pdf', 'vista'):
        abort(404)
    word = format == 'word'
    content = note.documento if word else note.pdf
    expected = note.documento_sha256 if word else note.pdf_sha256
    if sha256(content).hexdigest() != expected:
        abort(503, description='No se pudo verificar la integridad del documento archivado.')
    return private_download(content, f'nota_{note.numero}_{note.anio}.' + ('docx' if word else 'pdf'),
        DOCX_MIME if word else 'application/pdf', attachment=format != 'vista')
