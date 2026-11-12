"""Preparación de impresión separada del formulario original de Justificativos."""
from datetime import datetime
import re
from uuid import uuid4, UUID
from flask_wtf import FlaskForm
from wtforms import Form, StringField, HiddenField, IntegerField, BooleanField, SelectField, SelectMultipleField, FieldList, FormField
from wtforms.validators import Length, NumberRange, ValidationError
from app.administration.forms import RecordFilters, date_field, required
from app.employees.rules import paraguay_today
from app.extensions import db
from app.models.hospital_services import Servicio


class PrintFilters(RecordFilters):
    servicio = SelectField('Servicio o área', coerce=int, choices=[], default=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.servicio.choices = [(0, 'Todos los servicios')] + [(s.id, s.nombre) for s in
            db.session.scalars(db.select(Servicio).order_by(Servicio.nombre))]


class NoteSelectionForm(FlaskForm):
    registros = SelectMultipleField(coerce=int, choices=[], validate_choice=False, validators=[required()])
    confirmar = BooleanField('Confirmo que todos los registros seleccionados corresponden a días compensatorios por servicios extraordinarios.', validators=[required()])


def date_list(value):
    values = [v.strip() for v in re.split(r'[,;]', value or '')]
    if not values or len(values) > 31:
        raise ValueError('Utiliza de 1 a 31 fechas DD/MM/AAAA separadas por comas.')
    dates = [datetime.strptime(v, '%d/%m/%Y').date() for v in values]
    if len(set(dates)) != len(dates):
        raise ValueError('No repitas fechas dentro de una misma asignación.')
    return dates


class NoteRowForm(Form):
    justificativo_id = HiddenField(validators=[required()])
    version = HiddenField(validators=[required()])
    funcionario_id = SelectField('Funcionario verificado por cédula', coerce=int, choices=[], validators=[required()])
    fecha_realizacion = StringField('Fecha(s) de realización', validators=[required(), Length(max=370)])
    horario_cumplido = StringField('Horario cumplido', validators=[required(), Length(max=30)])
    fecha_libre = StringField('Fecha(s) del día libre', validators=[required(), Length(max=370)])
    horario_libre = StringField('Horario del día libre', validators=[required(), Length(max=30)])

    def validate_fecha_realizacion(self, field):
        try:
            date_list(field.data)
        except ValueError:
            raise ValidationError('Completa fechas válidas DD/MM/AAAA; separa varias fechas con comas, sin repetirlas.')

    validate_fecha_libre = validate_fecha_realizacion

    def validate_horario_cumplido(self, field):
        match = re.fullmatch(r'([0-2]\d:[0-5]\d)\s*(?:a|A|-)\s*([0-2]\d:[0-5]\d)', (field.data or '').strip())
        try:
            if not match:
                raise ValueError()
            start, end = (datetime.strptime(v, '%H:%M').time() for v in match.groups())
            if start == end:
                raise ValueError()
        except ValueError:
            raise ValidationError('Indica un horario válido como 06:00 a 12:00 o 18:00 a 06:00. Las horas deben ser distintas.')

    validate_horario_libre = validate_horario_cumplido


class NotePrintForm(FlaskForm):
    numero = IntegerField('Número de nota', validators=[required(), NumberRange(min=1, max=999999)])
    fecha_emision = date_field('Fecha de emisión')
    solicitud_id = HiddenField(default=lambda: str(uuid4()), validators=[required()])
    filas = FieldList(FormField(NoteRowForm), max_entries=200)
    confirmar = BooleanField('Verifiqué la cédula, las fechas, los horarios y la compensación por servicios extraordinarios de todas las filas.', validators=[required()])

    def validate_solicitud_id(self, field):
        try:
            UUID(field.data)
        except (ValueError, TypeError, AttributeError):
            raise ValidationError('Recarga la preparación de impresión.')

    def validate_filas(self, field):
        ids = [entry.form.justificativo_id.data for entry in field]
        if not ids or len(ids) != len(set(ids)):
            raise ValidationError('Selecciona justificativos distintos; cada registro se incluye una sola vez.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.fecha_emision.data and not self.is_submitted():
            self.fecha_emision.data = paraguay_today()
