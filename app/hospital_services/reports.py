from datetime import datetime
from flask import Blueprint, render_template, request, send_file, abort, current_app
from sqlalchemy.exc import SQLAlchemyError
from app.extensions import db
from app.dashboard_clock import PARAGUAY_TIMEZONE
from app.security.permissions import permission_required, can
from app.hospital_services.forms import ReportForm
from app.hospital_services.classification import audit, can_view_diagnosis
from app.hospital_services.records import CATEGORIES, matching_details
from app.hospital_services.report_data import collect_report, report_parameters, ReportTooLarge
from app.hospital_services.excel import generate_excel

bp = Blueprint('reports', __name__, url_prefix='/informes')


@bp.route('/', methods=['GET', 'POST'])
@permission_required('reports.export')
def index():
    if request.method == 'POST':
        # La autorización ya se comprobó. Un único snapshot evita duplicar un
        # movimiento reclasificado mientras se consultan todos los servicios.
        db.session.commit()
        db.session.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
    form = ReportForm()
    if request.method == 'GET':
        today = datetime.now(PARAGUAY_TIMEZONE).date()
        form.desde.data = today.replace(day=1)
        form.hasta.data = today
    data, error, status = None, None, 200
    if form.validate_on_submit():
        if form.categoria.data in ('completo', 'reposos') and not can_view_diagnosis():
            abort(403)
        action = request.form.get('accion')
        if action not in ('generar', 'previa', 'descargar'):
            abort(400)
        try:
            data = collect_report(form)
            params = report_parameters(form)
            if action == 'descargar':
                output = generate_excel(form, data)
                audit('INFORME_GENERADO', 'informes', details=params)
                audit('INFORME_DESCARGADO', 'informes', details=params)
                db.session.commit()
                response = send_file(output, as_attachment=True,
                    download_name=f'informe_enfermeria_{form.desde.data:%Y%m%d}_{form.hasta.data:%Y%m%d}.xlsx',
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', max_age=0)
                response.headers['Cache-Control'] = 'no-store, private, max-age=0'
                response.headers['X-Content-Type-Options'] = 'nosniff'
                return response
            audit('INFORME_GENERADO' if action == 'generar' else 'INFORME_VISTA_PREVIA', 'informes', details=params)
            html = render_template('hospital_services/reports.html', page_title='Informes Excel', form=form,
                report=data, categories=CATEGORIES, matching_details=matching_details, save_error=None)
            db.session.commit()
            return html
        except ReportTooLarge as exc:
            error, status, data = str(exc), 413, None
        except SQLAlchemyError as exc:
            db.session.rollback()
            current_app.logger.error('Error de informe (%s)', type(exc).__name__)
            error, status, data = 'No se pudo generar el informe. Revisa la conexión y vuelve a intentarlo.', 503, None
    elif request.method == 'POST':
        status = 422
    return render_template('hospital_services/reports.html', page_title='Informes Excel', form=form,
        report=data, categories=CATEGORIES, matching_details=matching_details, save_error=error), status
