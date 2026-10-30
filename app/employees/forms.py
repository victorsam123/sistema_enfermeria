from uuid import UUID, uuid4
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, HiddenField, SelectField
from wtforms.validators import Length, ValidationError
from app.administration.forms import clean_name, required, date_field
from app.documents.images import photos_field
from app.employees.rules import normalize_cedula, paraguay_today
from app.employees.careers import CAREER_CHOICES
from app.hospital_services.classification import ServiceField


class SearchForm(FlaskForm):
    cedula = StringField('INGRESE NÚMERO DE CÉDULA', validators=[required(), Length(max=20)])

    def validate_cedula(self, field):
        try:
            field.data = normalize_cedula(field.data)
        except ValueError as exc:
            raise ValidationError(str(exc))


class EmployeePhotoForm(FlaskForm):
    fotografias = photos_field()
    solicitud_id = HiddenField(default=lambda: str(uuid4()), validators=[required()])
    version = HiddenField()

    def validate_solicitud_id(self, field):
        try:
            if not field.raw_data:
                raise ValueError()
            UUID(field.data)
        except (ValueError, TypeError, AttributeError):
            raise ValidationError('Recarga el formulario antes de guardar.')

    def validate_fotografias(self, field):
        if len(getattr(field, 'prepared', [])) > 1:
            raise ValidationError('La ficha admite una sola fotografía personal. Selecciona una imagen.')


class EmployeeForm(EmployeePhotoForm):
    nombres = StringField('Nombres completos', filters=[clean_name], validators=[required(), Length(min=1, max=120)])
    apellidos = StringField('Apellidos completos', filters=[clean_name], validators=[required(), Length(min=1, max=120)])
    cedula = SearchForm.cedula
    fecha_nacimiento = date_field('Fecha de nacimiento')
    direccion_actual = TextAreaField('Dirección actual', filters=[lambda v: (v or '').strip()], validators=[required(), Length(max=500)])
    fecha_ingreso = date_field('Fecha exacta de ingreso a la institución')
    carrera = SelectField('Carrera', choices=[('', 'Selecciona una carrera')] + list(CAREER_CHOICES),
        validators=[required()])
    servicio_id = ServiceField('Servicio hospitalario')

    validate_cedula = SearchForm.validate_cedula

    def __init__(self, *args, **kwargs):
        record = kwargs.get('obj')
        self._employee = record
        super().__init__(*args, **kwargs)
        if record:
            del self.fecha_ingreso
        if record and record.servicio_id not in {key for key, _ in self.servicio_id.choices}:
            self.servicio_id.choices.append((record.servicio_id, record.servicio.nombre + ' (inactivo; conservar)'))

    def validate_apellidos(self, field):
        if len(f'{self.nombres.data} {field.data}') > 180:
            raise ValidationError('Los nombres y apellidos juntos deben tener como máximo 180 caracteres.')

    def validate_fecha_nacimiento(self, field):
        if field.data and field.data > paraguay_today():
            raise ValidationError('La fecha de nacimiento no puede ser futura.')
        if self._employee and field.data:
            dates = [self._employee.fecha_ingreso] + [v.fecha_ingreso for v in self._employee.vinculos]
            if any(d < field.data for d in dates):
                raise ValidationError('El nacimiento no puede ser posterior a las fechas de ingreso registradas.')

    def validate_fecha_ingreso(self, field):
        if field.data and field.data > paraguay_today():
            raise ValidationError('La fecha de ingreso no puede ser futura.')
        if field.data and self.fecha_nacimiento.data and field.data < self.fecha_nacimiento.data:
            raise ValidationError('El ingreso no puede ser anterior al nacimiento.')
