from wtforms import StringField, TextAreaField, HiddenField, SelectField
from wtforms.validators import Length, ValidationError
from app.administration.forms import SubmissionForm, RecordFilters, clean_name, required, date_field
from app.administration.vacation_rules import vacation_days


class ComisionadoForm(SubmissionForm):
    nombres_apellidos = StringField('Nombres y Apellidos', filters=[clean_name],
        validators=[required(), Length(min=3, max=180, message='Utiliza entre 3 y 180 caracteres.')])
    fecha_inasistencia = date_field('Fecha de inasistencia')
    motivo = TextAreaField('Motivo', filters=[lambda v: (v or '').strip()],
        validators=[required(), Length(min=3, max=2000, message='Utiliza entre 3 y 2000 caracteres.')])
    lugar = StringField('Lugar', filters=[clean_name],
        validators=[required(), Length(min=2, max=250, message='Utiliza entre 2 y 250 caracteres.')])
    version = HiddenField()


class VacacionForm(SubmissionForm):
    nombres_apellidos = StringField('Nombres y Apellidos', filters=[clean_name],
        validators=[required(), Length(min=3, max=180, message='Utiliza entre 3 y 180 caracteres.')])
    fecha_inicio = date_field('Fecha de inicio de vacaciones')
    fecha_termino = date_field('Fecha de término de vacaciones')
    version = HiddenField()

    def validate_funcionario_id(self, field):
        super().validate_funcionario_id(field)
        if not field.data:
            raise ValidationError('Selecciona la ficha del funcionario para completar la planilla de vacaciones.')

    def validate_fecha_termino(self, field):
        if self.fecha_inicio.data and field.data:
            try:
                vacation_days(self.fecha_inicio.data, field.data)
            except ValueError as exc:
                raise ValidationError(str(exc))


class LeaveFilters(RecordFilters):
    orden = SelectField('Orden por fecha', choices=[('asc', 'Más antiguas primero'), ('desc', 'Más recientes primero')])
