from uuid import UUID
from flask import abort, flash, redirect, url_for
from flask_login import current_user
from app.extensions import db
from app.security.permissions import can
from app.hospital_services.classification import saved_message


def get_live_record(model, record_id):
    record = db.get_or_404(model, record_id)
    if record.eliminado:
        abort(404)
    return record


def loading_confirmation(model, request_id, endpoint):
    if can('records.read'):
        return None
    item = db.session.execute(db.select(model.id, model.servicio_id).where(
        model.solicitud_id == UUID(request_id), model.usuario_registro_id == current_user.id)).one()
    flash(f'{saved_message(item.servicio_id)}. Código del registro: {model.__tablename__.upper()}-{item.id}', 'success')
    return redirect(url_for(endpoint), code=303)
