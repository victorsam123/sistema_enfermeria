from uuid import uuid4, UUID
import unicodedata
from flask_wtf import FlaskForm
from flask import g
from app.documents.images import photos_field
from app.hospital_services.classification import ServiceField
from wtforms import Form, StringField, TextAreaField, DateField, TimeField, HiddenField, FieldList, FormField, SelectField
from wtforms.validators import DataRequired, Length, Optional, ValidationError


def clean_name(value):
    return ' '.join(unicodedata.normalize('NFKC', value or '').split())


def name_key(value):
    return clean_name(value).casefold()


def required():
    return DataRequired(message='Completa este campo obligatorio.')


def date_field(label, optional=False):
    return DateField(label, format='%d/%m/%Y', validators=[Optional() if optional else required()],
                     render_kw={'placeholder': 'DD/MM/AAAA', 'inputmode': 'numeric',
                                'pattern': r'\d{2}/\d{2}/\d{4}', 'maxlength': 10})


class SubmissionForm(FlaskForm):
    funcionario_id = HiddenField()
    fotografias = photos_field()
    adjuntos_lote = HiddenField(default=lambda: str(uuid4()))
    servicio_id = ServiceField('Servicio hospitalario')
    solicitud_id = HiddenField(validators=[required()], default=lambda: str(uuid4()))

    def __init__(self, *args, **kwargs):
        self._linked_record = kwargs.get('obj')
        super().__init__(*args, **kwargs)

    def validate_funcionario_id(self, field):
        from app.employees.lookup import validate_record_link
        validate_record_link(self, field)

    def validate_adjuntos_lote(self, field):
        if self.fotografias.data and any(getattr(f, 'filename', '') for f in self.fotografias.data):
            try:
                if not field.raw_data:
                    raise ValueError()
                g.document_batch = UUID(field.data)
            except (ValueError, TypeError, AttributeError):
                raise ValidationError('Recarga el formulario para adjuntar documentos.')

    def validate_solicitud_id(self, field):
        if not field.raw_data:
            raise ValidationError('Falta la identificación del formulario. Recarga la página.')
        try:
            UUID(field.data)
        except (ValueError, TypeError, AttributeError):
            raise ValidationError('El formulario no es válido. Recarga la página.')


class JustificativoForm(SubmissionForm):
    nombres_apellidos = StringField('Nombres y Apellidos', filters=[clean_name],
        validators=[required(), Length(min=3, max=180, message='Utiliza entre 3 y 180 caracteres.')])
    fecha_inasistencia = date_field('Fecha del día libre o inasistencia')
    motivo = TextAreaField('Motivo', filters=[lambda v: (v or '').strip()],
        validators=[required(), Length(min=3, max=2000, message='Describe el motivo con entre 3 y 2000 caracteres.')])
    fecha_cobertura = date_field('Fecha de cobertura', optional=True)
    version = HiddenField()


class GuardiaDetailForm(Form):
    detalle_id = HiddenField()
    participante = SelectField('Funcionario correspondiente', choices=[('S', 'Solicitante (S)'), ('R', 'Reemplazante (R)')], validators=[required()])
    fecha_guardia = date_field('Fecha de guardia')
    hora_inicio = TimeField('Hora de inicio', format='%H:%M', validators=[required()])
    hora_fin = TimeField('Hora de finalización', format='%H:%M', validators=[required()])
    codigo = SelectField('Código de registro', choices=[('', 'Sin código'), ('S', 'S'), ('R', 'R'), ('G', 'G'), ('L', 'L')])

    def validate_detalle_id(self, field):
        if field.data and (not field.data.isdecimal() or len(field.data) > 10):
            raise ValidationError('Identificador de fecha no válido.')

    def validate_hora_fin(self, field):
        if field.data and field.data == self.hora_inicio.data:
            raise ValidationError('Las horas de inicio y finalización deben ser distintas.')


class CambioGuardiaForm(SubmissionForm):
    solicitante_funcionario_id = HiddenField()
    reemplazante_funcionario_id = HiddenField()
    solicitante = StringField('Nombres y Apellidos del Solicitante (S)', filters=[clean_name],
        validators=[required(), Length(min=3, max=180, message='Utiliza entre 3 y 180 caracteres.')])
    reemplazante = StringField('Nombres y Apellidos del Reemplazante (R)', filters=[clean_name],
        validators=[required(), Length(min=3, max=180, message='Utiliza entre 3 y 180 caracteres.')])
    detalles = FieldList(FormField(GuardiaDetailForm), min_entries=2)
    version = HiddenField()

    def validate_solicitante_funcionario_id(self, field):
        from app.employees.lookup import validate_record_link
        validate_record_link(self, field, 'solicitante')

    def validate_reemplazante_funcionario_id(self, field):
        from app.employees.lookup import validate_record_link
        validate_record_link(self, field, 'reemplazante')
        solic = str(self.solicitante_funcionario_id.data or '')
        if field.data and solic.isascii() and solic.isdecimal() and int(field.data) == int(solic):
            raise ValidationError('El solicitante y el reemplazante deben ser personas distintas.')

    def validate_reemplazante(self, field):
        if name_key(self.solicitante.data) == name_key(field.data):
            raise ValidationError('El solicitante y el reemplazante deben ser personas distintas.')

    def validate_detalles(self, field):
        if len(field.entries) < 2 or field.entries[0].form.participante.data != 'S' or field.entries[1].form.participante.data != 'R':
            raise ValidationError('Completa las secciones del solicitante y del reemplazante.')
        seen = set()
        ids = set()
        for entry in field.entries:
            row = entry.form
            identity = (row.participante.data, row.fecha_guardia.data, row.hora_inicio.data, row.hora_fin.data, row.codigo.data or None)
            if identity in seen:
                raise ValidationError('Hay una fecha, funcionario, horario y código repetidos. Revisa las filas antes de guardar.')
            seen.add(identity)
            if row.detalle_id.data:
                if row.detalle_id.data in ids:
                    raise ValidationError('No se puede repetir el identificador de una fecha.')
                ids.add(row.detalle_id.data)


class RecordFilters(FlaskForm):
    q = StringField('Buscar por nombre', filters=[clean_name], validators=[Optional(), Length(max=180)])
    desde = date_field('Desde', optional=True)
    hasta = date_field('Hasta', optional=True)

    def validate_hasta(self, field):
        if field.data and self.desde.data and field.data < self.desde.data:
            raise ValidationError('La fecha hasta debe ser igual o posterior a la fecha desde.')
