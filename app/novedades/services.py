from datetime import date, datetime, timedelta
import calendar

from sqlalchemy.orm import selectinload

from app.dashboard_clock import PARAGUAY_TIMEZONE
from app.extensions import db
from app.models.employees import Funcionario
from app.models.leave_records import Vacacion


def _as_paraguay_date(value=None):
    if value is None:
        return datetime.now(PARAGUAY_TIMEZONE).date()
    if isinstance(value, datetime):
        return value.astimezone(PARAGUAY_TIMEZONE).date() if value.tzinfo else value.replace(tzinfo=PARAGUAY_TIMEZONE).date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def _next_birthday(funcionario, today):
    birth_date = funcionario.fecha_nacimiento
    birthday_day = birth_date.day
    if birth_date.month == 2 and birth_date.day == 29 and not calendar.isleap(today.year):
        birthday_day = 28
    annual_birthday = date(today.year, birth_date.month, birthday_day)
    if annual_birthday < today:
        next_year_day = birth_date.day
        if birth_date.month == 2 and birth_date.day == 29 and not calendar.isleap(today.year + 1):
            next_year_day = 28
        annual_birthday = date(today.year + 1, birth_date.month, next_year_day)
    return annual_birthday


def _service_name_for_employee(funcionario):
    if funcionario and funcionario.servicio:
        return funcionario.servicio.nombre
    return 'Servicio no informado'


def _service_name_for_vacation(vacacion):
    if vacacion.funcionario and vacacion.funcionario.servicio:
        return vacacion.funcionario.servicio.nombre
    if vacacion.servicio:
        return vacacion.servicio.nombre
    return 'Servicio no informado'


def get_birthdays(today=None):
    today = _as_paraguay_date(today)
    today_birthdays = []
    upcoming_birthdays = []
    employees = db.session.scalars(
        db.select(Funcionario).order_by(Funcionario.apellidos, Funcionario.nombres)
    ).all()
    for employee in employees:
        next_birthday = _next_birthday(employee, today)
        days_until = (next_birthday - today).days
        record = {
            'funcionario_id': employee.id,
            'nombre': employee.nombre_completo.strip(),
            'servicio': _service_name_for_employee(employee),
            'fecha_cumpleanos': next_birthday,
            'dias_restantes': days_until,
        }
        if next_birthday == today:
            record['mensaje'] = '¡Hoy está de cumpleaños!'
            today_birthdays.append(record)
        elif 1 <= days_until <= 8:
            record['mensaje'] = f'Faltan {days_until} días.'
            upcoming_birthdays.append(record)
    today_birthdays.sort(key=lambda item: (item['nombre']))
    upcoming_birthdays.sort(key=lambda item: (item['dias_restantes'], item['nombre']))
    return today_birthdays, upcoming_birthdays


def get_upcoming_vacations(today=None):
    today = _as_paraguay_date(today)
    window_end = today + timedelta(days=15)
    records = db.session.scalars(
        db.select(Vacacion)
        .options(selectinload(Vacacion.funcionario).selectinload(Funcionario.servicio), selectinload(Vacacion.servicio))
        .where(Vacacion.eliminado.is_(False), Vacacion.fecha_inicio >= today, Vacacion.fecha_inicio <= window_end)
        .order_by(Vacacion.fecha_inicio.asc(), Vacacion.nombres_apellidos.asc())
    ).all()
    result = []
    for vacacion in records:
        days_until = (vacacion.fecha_inicio - today).days
        if days_until < 0:
            continue
        nombre = vacacion.nombres_apellidos.strip() if vacacion.nombres_apellidos else (
            vacacion.funcionario.nombre_completo.strip() if vacacion.funcionario else 'Funcionario no registrado'
        )
        if days_until == 0:
            mensaje = 'Inicia sus vacaciones hoy'
        elif 1 <= days_until <= 7:
            mensaje = f'Vacaciones próximas: faltan {days_until} días'
        else:
            mensaje = f'Próximas vacaciones: faltan {days_until} días'
        result.append({
            'funcionario_id': vacacion.funcionario_id,
            'nombre': nombre,
            'servicio': _service_name_for_vacation(vacacion),
            'fecha_inicio': vacacion.fecha_inicio,
            'fecha_termino': vacacion.fecha_termino,
            'total_dias': vacacion.total_dias,
            'dias_restantes': days_until,
            'mensaje': mensaje,
        })
    return result


def get_novedades_snapshot(today=None):
    today = _as_paraguay_date(today)
    birthday_today, upcoming_birthdays = get_birthdays(today)
    forthcoming_vacations = get_upcoming_vacations(today)
    return {
        'fecha_actual': today,
        'cumpleanos_hoy': birthday_today,
        'proximos_cumpleanos': upcoming_birthdays,
        'vacaciones_proximas': forthcoming_vacations,
        'resumen': {
            'cumpleanos_hoy': len(birthday_today),
            'proximos_cumpleanos': len(upcoming_birthdays),
            'vacaciones_proximas': len(forthcoming_vacations),
        },
    }
