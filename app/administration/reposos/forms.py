from wtforms import StringField, TextAreaField, HiddenField, SelectField
from wtforms.validators import Length, ValidationError
from app.administration.forms import SubmissionForm, RecordFilters, clean_name, required, date_field
from app.administration.reposos.rules import rest_days


class ReposoForm(SubmissionForm):
    nombres_apellidos = StringField('Nombres y Apellidos', filters=[clean_name],
        validators=[required(), Length(min=3, max=180, message='Utiliza entre 3 y 180 caracteres.')])
    fecha_desde = date_field('Fecha desde')
    fecha_hasta = date_field('Fecha hasta')
    diagnostico = TextAreaField('Diagnóstico', filters=[lambda v: (v or '').strip()],
        validators=[required(), Length(min=1, max=2000, message='Utiliza hasta 2000 caracteres.')])
    fecha_entrega_departamento = date_field('Fecha de entrega al Departamento')
    version = HiddenField()

    def validate_fecha_hasta(self, field):
        if self.fecha_desde.data and field.data:
            try:
                rest_days(self.fecha_desde.data, field.data)
            except ValueError as exc:
                raise ValidationError(str(exc))


class ReposoFilters(RecordFilters):
    orden = SelectField('Ordenar registros', default='desde_desc', choices=[
        ('desde_desc', 'Fecha desde: más reciente'), ('desde_asc', 'Fecha desde: más antigua'),
        ('creacion_desc', 'Carga: más reciente'), ('creacion_asc', 'Carga: más antigua'),
    ])
