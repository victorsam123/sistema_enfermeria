from uuid import UUID, uuid4
from flask_wtf import FlaskForm
from wtforms import HiddenField, TextAreaField, SelectField
from wtforms.validators import ValidationError, Length
from app.administration.forms import date_field, required
from app.employees.rules import paraguay_today


class EmploymentForm(FlaskForm):
    fecha_ingreso = date_field('Fecha de ingreso del vínculo')
    solicitud_id = HiddenField(default=lambda: str(uuid4()), validators=[required()])
    version = HiddenField(validators=[required()])

    def validate_solicitud_id(self, field):
        try:
            if not field.raw_data:
                raise ValueError()
            UUID(field.data)
        except (ValueError, TypeError, AttributeError):
            raise ValidationError('Recarga el formulario antes de guardar el vínculo.')

    def validate_fecha_ingreso(self, field):
        if field.data and field.data > paraguay_today():
            raise ValidationError('La fecha de ingreso no puede ser futura.')


class EmploymentStateForm(FlaskForm):
    version = HiddenField(validators=[required()])
    accion = HiddenField(validators=[required()])
    motivo = TextAreaField('Motivo del cambio de estado', filters=[lambda s: (s or '').strip()], validators=[required(), Length(min=3, max=1000)])
    confirmacion = SelectField('Confirmación', choices=[('', 'Selecciona una opción'), ('CONFIRMAR', 'Confirmar cambio de estado')], validators=[required()])
