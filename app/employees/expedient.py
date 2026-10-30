"""Expediente virtual por ID; no copia registros, documentos ni fotografías."""
from flask import render_template, request, url_for, abort
from app.extensions import db
from app.models.administration import CambioGuardia
from app.models.employees import Funcionario
from app.hospital_services.records import CATEGORIES, matching_details
from app.security.permissions import permission_required, require


def related_query(person_id, category):
    model = category.model
    query = db.select(model).where(model.eliminado.is_(False))
    if model is CambioGuardia:
        return query.where(model.tipo_cambio == category.kind, db.or_(
            model.solicitante_funcionario_id == person_id, model.reemplazante_funcionario_id == person_id))
    return query.where(model.funcionario_id == person_id)


def expediente_counts(person_id):
    items = []
    for key, category in CATEGORIES.items():
        rows = related_query(person_id, category).with_only_columns(category.model.id,
            category.model.documentos_count.label('documentos_count')).subquery()
        counts = db.session.execute(db.select(db.func.count(), db.func.coalesce(db.func.sum(rows.c.documentos_count), 0)).select_from(rows)).one()
        items.append({'key': key, 'label': category.label, 'total': counts[0], 'documents': counts[1]})
    return items


def register_expedient(bp):
    @bp.get('/<int:record_id>/expediente/<category_key>')
    @permission_required('employees.read')
    def expediente(record_id, category_key):
        require('records.read')
        if category_key == 'reposos':
            require('diagnoses.read')
        category = CATEGORIES.get(category_key)
        if category is None:
            abort(404)
        record = db.get_or_404(Funcionario, record_id)
        query = related_query(record.id, category).order_by(category.model.fecha_creacion.desc(), category.model.id.desc())
        rows = db.paginate(query, page=max(1, request.args.get('page', 1, type=int)), per_page=20, error_out=False)
        return render_template('employees/expedient.html', page_title=category.label + ' · Expediente personal',
            record=record, category=category, category_key=category_key, rows=rows, matching_details=matching_details)
