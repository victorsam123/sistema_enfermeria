"""Lectura acotada de movimientos reales; nunca se filtra por fecha de carga."""
from flask import current_app
from app.extensions import db
from app.models.hospital_services import Servicio, PENDING_CODE
from app.hospital_services.records import CATEGORIES, record_query, matching_details


class ReportTooLarge(ValueError):
    pass


def collect_report(form):
    services_query = db.select(Servicio).order_by(Servicio.id)
    if form.servicio_id.data:
        services_query = services_query.where(Servicio.id == form.servicio_id.data)
    categories = CATEGORIES if form.categoria.data == 'completo' else {form.categoria.data: CATEGORIES[form.categoria.data]}
    result, row_count = [], 0
    limit = current_app.config.get('MAX_REPORT_ROWS', 50000)
    for service in db.session.scalars(services_query):
        data = {}
        for key, category in categories.items():
            rows = db.session.scalars(record_query(category, service.id, form.desde.data, form.hasta.data).limit(limit + 1)).all()
            row_count += sum(len(matching_details(r, form.desde.data, form.hasta.data)) for r in rows) if category.kind else len(rows)
            if len(rows) > limit or row_count > limit:
                raise ReportTooLarge(f'El informe supera {limit:,} filas. Reduce el período o selecciona un servicio o categoría.')
            data[key] = rows
        if service.codigo == PENDING_CODE and not form.servicio_id.data and not any(data.values()):
            continue
        result.append({'service': service, 'records': data})
    return result


def report_parameters(form):
    return {'desde': form.desde.data.isoformat(), 'hasta': form.hasta.data.isoformat(),
        'servicio_id': form.servicio_id.data, 'categoria': form.categoria.data}
