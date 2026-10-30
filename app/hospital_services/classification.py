from flask_login import current_user
from app.security.permissions import can
from wtforms import SelectField
from wtforms.validators import ValidationError
from app.extensions import db
from app.models import utcnow
from app.models.hospital_services import Servicio, HistorialAdministrativo, PENDING_CODE


def active_services():
    return db.session.scalars(db.select(Servicio).where(Servicio.activo.is_(True),
        Servicio.codigo != PENDING_CODE).order_by(Servicio.id)).all()


class ServiceField(SelectField):
    """Opciones calculadas por petición; un POST no puede inventar un servicio."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, choices=[], coerce=int, **kwargs)

    def process(self, *args, **kwargs):
        self.choices = [(0, 'Selecciona un servicio')] + [(s.id, s.nombre) for s in active_services()]
        super().process(*args, **kwargs)

    def pre_validate(self, form):
        super().pre_validate(form)
        if not self.data:
            raise ValidationError('Selecciona el servicio antes de guardar este registro.')


def audit(event, entity, record_id=None, old_service=None, new_service=None, details=None, user_id=None):
    db.session.add(HistorialAdministrativo(evento=event, entidad=entity, registro_id=record_id,
        usuario_id=user_id if user_id is not None else current_user.id,
        servicio_anterior_id=old_service, servicio_nuevo_id=new_service, detalles=details or {}))


def apply_service(record, service_id, user_id):
    if record.servicio_id != service_id:
        audit('RECLASIFICACION', record.__tablename__, record.id, record.servicio_id, service_id, user_id=user_id)
        record.servicio_id = service_id


def saved_message(service_id):
    service = db.session.get(Servicio, service_id)
    return f'Registro guardado correctamente en el servicio {service.nombre}'


def can_view_diagnosis():
    # Política explícita y centralizada, ampliable cuando se definan otros roles.
    return can('diagnoses.read')
