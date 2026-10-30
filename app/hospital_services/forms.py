from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, BooleanField, HiddenField
from wtforms.validators import Length, Regexp, Optional, ValidationError
from app.administration.forms import date_field, required, clean_name
from app.models.hospital_services import Servicio
from app.extensions import db
from app.hospital_services.classification import ServiceField
from app.hospital_services.records import CATEGORIES


class ServiceForm(FlaskForm):
    nombre = StringField('Nombre del servicio', filters=[clean_name], validators=[required(), Length(min=2, max=120)])
    codigo = StringField('Código permanente', filters=[lambda v: (v or '').strip().upper()],
        validators=[required(), Regexp(r'^[A-Z0-9][A-Z0-9_-]{1,39}$', message='Usa de 2 a 40 letras A-Z, números, guion o guion bajo.')])
    activo = BooleanField('Servicio activo', default=True)
    version = HiddenField()


class ReclassifyForm(FlaskForm):
    servicio_id = ServiceField('Nuevo servicio')
    version = HiddenField(validators=[required()])


class ReportForm(FlaskForm):
    desde = date_field('Fecha desde')
    hasta = date_field('Fecha hasta')
    servicio_id = SelectField('Servicio', coerce=int, choices=[])
    categoria = SelectField('Tipo de informe', choices=[('completo', 'Informe completo')] + [(k, v.label) for k, v in CATEGORIES.items()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.servicio_id.choices = [(0, 'TODOS LOS SERVICIOS')] + [
            (s.id, s.nombre + (' (inactivo)' if not s.activo and s.codigo != 'PENDIENTE' else ''))
            for s in db.session.scalars(db.select(Servicio).order_by(Servicio.id))]

    def validate_hasta(self, field):
        if field.data and self.desde.data and field.data < self.desde.data:
            raise ValidationError('La fecha hasta debe ser igual o posterior a la fecha desde.')
