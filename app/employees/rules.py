"""Identidad local y diferencias de calendario, sin consultas externas."""
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
from app.dashboard_clock import PARAGUAY_TIMEZONE


def paraguay_today():
    return datetime.now(PARAGUAY_TIMEZONE).date()


def normalize_cedula(value):
    value = (value or '').strip()
    if not re.fullmatch(r'(?:[0-9]{1,12}|[0-9]{1,3}(?:\.[0-9]{3}){1,3})', value):
        raise ValueError('Ingresa una cédula de hasta 12 dígitos, con o sin puntos de miles.')
    normalized = value.replace('.', '').lstrip('0')
    if not normalized:
        raise ValueError('El número de cédula debe ser mayor que cero.')
    return normalized


def completed_age(birth, today=None):
    today = today or paraguay_today()
    if birth > today:
        raise ValueError('La fecha de nacimiento no puede ser futura.')
    return relativedelta(today, birth).years


def seniority(entry, today=None):
    if entry is None:
        return None
    today = today or paraguay_today()
    if entry > today:
        raise ValueError('La fecha de ingreso no puede ser futura.')
    delta = relativedelta(today, entry)
    return delta.years, delta.months, delta.days
