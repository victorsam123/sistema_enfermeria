from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, HiddenField, TextAreaField
from wtforms.validators import Length, Regexp, EqualTo, Optional
from app.administration.forms import clean_name, required
from app.security.permissions import ROLE_LABELS, manageable_roles
from app.security.passwords import secure_password, username_filter


class UserForm(FlaskForm):
    nombre = StringField('Nombres y Apellidos', filters=[clean_name], validators=[required(), Length(min=3, max=120)])
    username = StringField('Nombre de usuario', filters=[username_filter], validators=[required(),
        Regexp(r'^[a-z0-9][a-z0-9_.-]{2,79}$', message='Usa de 3 a 80 letras, números, punto, guion o guion bajo.')])
    rol = SelectField('Rol del usuario', choices=[], default='OPERADOR')
    activo = SelectField('Estado', choices=[('1', 'Activo'), ('0', 'Inactivo')], validators=[required()], default='1')
    version = HiddenField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rol.choices = [(r, ROLE_LABELS[r]) for r in manageable_roles()]


class NewUserForm(UserForm):
    password = PasswordField('Contraseña inicial', validators=[required(), secure_password])
    confirm_password = PasswordField('Confirmar contraseña', validators=[required(), EqualTo('password', message='Las contraseñas no coinciden.')])


class ResetPasswordForm(FlaskForm):
    password = PasswordField('Nueva contraseña temporal', validators=[required(), secure_password])
    confirm_password = PasswordField('Confirmar contraseña', validators=[required(), EqualTo('password', message='Las contraseñas no coinciden.')])
    version = HiddenField(validators=[required()])


class OwnPasswordForm(FlaskForm):
    actual = PasswordField('Contraseña actual', validators=[required(), Length(max=256)])
    password = PasswordField('Nueva contraseña', validators=[required(), secure_password])
    confirm_password = PasswordField('Confirmar contraseña', validators=[required(), EqualTo('password', message='Las contraseñas no coinciden.')])


class AccountStateForm(FlaskForm):
    version = HiddenField(validators=[required()])
    confirmacion = SelectField('Confirmación', choices=[('', 'Selecciona una opción'), ('CONFIRMAR', 'Confirmar cambio de estado')], validators=[required()])


class UserFilters(FlaskForm):
    q = StringField('Buscar nombre o usuario', filters=[clean_name], validators=[Optional(), Length(max=120)])
    rol = SelectField('Rol', choices=[], default='')
    estado = SelectField('Estado', choices=[('', 'Todos'), ('1', 'Activos'), ('0', 'Inactivos')], default='')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rol.choices = [('', 'Todos')] + [(r, ROLE_LABELS[r]) for r in manageable_roles()]
