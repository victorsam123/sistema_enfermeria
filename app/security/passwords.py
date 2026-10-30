import unicodedata
from wtforms.validators import ValidationError

PASSWORD_HELP = 'Utiliza de 12 a 128 caracteres, con mayúsculas, minúsculas y números. No uses tu nombre de usuario.'


def secure_password(form, field):
    value = field.data or ''
    username = getattr(getattr(form, 'username', None), 'data', '') or ''
    if (len(value) < 12 or len(value) > 128 or not any(c.isupper() for c in value)
            or not any(c.islower() for c in value) or not any(c.isdigit() for c in value)
            or value != value.strip() or (username and username.casefold() in value.casefold())):
        raise ValidationError(PASSWORD_HELP)


def username_filter(value):
    return unicodedata.normalize('NFKC', value or '').strip().lower()
