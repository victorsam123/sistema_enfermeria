"""Búsqueda operativa mínima, vinculada a un formulario y una sesión."""
import hashlib
import hmac
from datetime import timedelta
from uuid import UUID
from flask import current_app, session, request, abort
from flask_login import current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature
from sqlalchemy.dialects.postgresql import insert
from wtforms.validators import ValidationError
from app.extensions import db
from app.models import IntentoLogin, utcnow
from app.models.employees import Funcionario

SCOPES = {'justificativos': ('justificativos.index', 'justificativos.edit'),
    'reposos': ('reposo.index', 'reposo.edit'), 'guardias': ('guardias.normal', 'guardias.normal_edit'),
    'pagadas': ('guardias.pagada', 'guardias.pagada_edit'), 'vacaciones': ('vacaciones.index', 'vacaciones.edit'),
    'comisionados': ('comisionados.index', 'comisionados.edit')}


def signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='funcionario-carga-v1')


def session_binding():
    return hashlib.sha256((session.get('credential_version', '') + session.get('csrf_token', '')).encode()).hexdigest()


def lookup_ticket(form):
    scope = next((key for key, endpoints in SCOPES.items() if request.endpoint in endpoints), None)
    if scope is None:
        return ''
    return signer().dumps({'usuario': current_user.id, 'sesion': session_binding(),
        'modulo': scope, 'formulario': str(form.solicitud_id.data)})


def validate_ticket(token):
    if not isinstance(token, str) or len(token) > 4096:
        abort(403)
    try:
        data = signer().loads(token, max_age=1800)
        UUID(data['formulario'])
        if (data['usuario'] != current_user.id or data['sesion'] != session_binding() or data['modulo'] not in SCOPES):
            raise ValueError()
    except (BadSignature, KeyError, TypeError, ValueError):
        abort(403)


def consume_lookup():
    # Contador compartido, sin cédula, nombre, dirección ni diagnóstico.
    now = utcnow()
    key = hmac.new(current_app.secret_key.encode(), f'employee-lookup:{current_user.id}'.encode(), hashlib.sha256).hexdigest()
    db.session.execute(insert(IntentoLogin).values(clave=key, inicio=now, cantidad=0).on_conflict_do_nothing())
    row = db.session.scalar(db.select(IntentoLogin).where(IntentoLogin.clave == key).with_for_update())
    if now - row.inicio >= timedelta(minutes=1):
        row.inicio, row.cantidad = now, 0
    allowed = row.cantidad < 30
    if allowed:
        row.cantidad += 1
    db.session.commit()
    return allowed


def validate_record_link(form, field, name_field='nombres_apellidos'):
    if not field.data:
        return
    value = str(field.data)
    if not value.isascii() or not value.isdigit() or len(value) > 10:
        raise ValidationError('La ficha seleccionada no es válida. Busca nuevamente por cédula.')
    if not hasattr(form, name_field):
        raise ValidationError('Selecciona la ficha en la sección del funcionario correspondiente.')
    person = db.session.get(Funcionario, int(value))
    if person is None:
        raise ValidationError('La ficha seleccionada no existe.')
    record = getattr(form, '_linked_record', None)
    old_name = getattr(record, name_field, None)
    old_id = getattr(record, field.name, None)
    name = getattr(form, name_field).data
    # Un registro histórico conserva el nombre documentado aunque después
    # cambie la ficha. Una asociación nueva exige el nombre de la ficha.
    if name != person.nombre_completo and not (record and old_id == person.id and old_name == name):
        raise ValidationError('El nombre no coincide con la ficha seleccionada. Busca nuevamente o quita el vínculo.')


def record_links(form):
    names = ('solicitante_funcionario_id', 'reemplazante_funcionario_id') if hasattr(form, 'solicitante') else ('funcionario_id',)
    return {key: int(getattr(form, key).data) if getattr(form, key).data else None for key in names}
