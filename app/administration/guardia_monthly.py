"""Serialized, persistent monthly quota allocations for guardia records."""
from datetime import date

from sqlalchemy import inspect

from app.extensions import db
from app.models import utcnow
from app.models.administration import CambioGuardia, CambioGuardiaCupo
from app.administration.forms import name_key

LIMITS = {'REEMPLAZO': 2, 'PAGADA': 1, 'EMERGENCIA': 1}
LABELS = {'REEMPLAZO': 'con reemplazante', 'PAGADA': 'pagados', 'EMERGENCIA': 'de emergencia'}
MONTH_NAMES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
QUOTA_ROLES = {'REEMPLAZO': ('solicitante', 'reemplazante'),
               'PAGADA': ('solicitante',), 'EMERGENCIA': ('solicitante',)}


class GuardiaValidation(ValueError):
    pass


class AdvanceConfirmation(GuardiaValidation):
    pass


def require_advance_confirmation(plans, confirmed):
    advanced = [plan for plan in plans if plan['uso_anticipado']]
    if advanced and not confirmed:
        names = ', '.join(dict.fromkeys(plan['funcionario_nombre'] for plan in advanced))
        target_month = max((plan['anio_imputacion'], plan['mes_imputacion']) for plan in advanced)
        raise AdvanceConfirmation(
            f'{names} ha agotado sus cupos del mes actual. Este cambio será descontado del cupo de '
            f'{MONTH_NAMES[target_month[1] - 1]} de {target_month[0]}. Confirma para continuar.')


def lock_monthly():
    # All quota writes use the same transaction-scoped lock.
    db.session.execute(db.text('SELECT pg_advisory_xact_lock(901,12)'))


def _allocation_table_exists():
    return inspect(db.session.get_bind()).has_table(CambioGuardiaCupo.__tablename__)


def next_month(day):
    year = day.year + (day.month == 12)
    month = day.month % 12 + 1
    return date(year, month, 1)


def _name_matches(left, right):
    return bool(left and right and name_key(left) == name_key(right))


def _matches_employee(allocation, name, employee_id, aliases):
    if employee_id and allocation.funcionario_id == int(employee_id):
        return True
    return allocation.funcionario_id is None and name_key(allocation.funcionario_nombre) in aliases


def _allocation_usage(name, employee_id, period, exclude=None):
    aliases = {name_key(name)} if name else set()
    if employee_id:
        from app.models.employees import Funcionario
        employee = db.session.get(Funcionario, employee_id)
        if employee:
            aliases.add(name_key(employee.nombre_completo))
    result = dict.fromkeys(LIMITS, 0)
    allocations = db.session.scalars(
        db.select(CambioGuardiaCupo).join(CambioGuardia).where(
            CambioGuardia.eliminado.is_(False),
            CambioGuardia.id != exclude if exclude is not None else db.true(),
            CambioGuardiaCupo.anio_imputacion == period.year,
            CambioGuardiaCupo.mes_imputacion == period.month,
        )
    )
    for allocation in allocations:
        if allocation.tipo_cupo in result and _matches_employee(allocation, name, employee_id, aliases):
            result[allocation.tipo_cupo] += 1
    return result


def _legacy_usage(name, employee_id, period, exclude=None):
    start = date(period.year, period.month, 1)
    end = next_month(start)
    rows = db.session.scalars(db.select(CambioGuardia).where(
        CambioGuardia.eliminado.is_(False), CambioGuardia.fecha_cambio >= start,
        CambioGuardia.fecha_cambio < end, CambioGuardia.tipo_cambio.in_(LIMITS),
        CambioGuardia.id != exclude if exclude is not None else db.true()))
    aliases = {name_key(name)}
    if employee_id:
        from app.models.employees import Funcionario
        person = db.session.get(Funcionario, employee_id)
        if person:
            aliases.add(name_key(person.nombre_completo))
    result = dict.fromkeys(LIMITS, 0)
    for row in rows:
        for role in QUOTA_ROLES[row.tipo_cambio]:
            linked = getattr(row, role + '_funcionario_id')
            matches = linked == employee_id if linked and employee_id else name_key(getattr(row, role)) in aliases
            if matches:
                result[row.tipo_cambio] += 1
                break
    return result


def monthly_usage(name, employee_id, day, exclude=None):
    period = date(day.year, day.month, 1)
    if not _allocation_table_exists():
        return _legacy_usage(name, employee_id, period, exclude)
    return _allocation_usage(name, employee_id, period, exclude)


def monthly_snapshot(name, employee_id, reference_day, exclude=None):
    current_period = date(reference_day.year, reference_day.month, 1)
    following_period = next_month(current_period)
    current = monthly_usage(name, employee_id, current_period, exclude)
    following = monthly_usage(name, employee_id, following_period, exclude)
    advance_used = dict.fromkeys(LIMITS, 0)
    if _allocation_table_exists():
        rows = db.session.scalars(db.select(CambioGuardiaCupo).join(
            CambioGuardia, CambioGuardia.id == CambioGuardiaCupo.cambio_guardia_id
        ).where(CambioGuardia.eliminado.is_(False),
            CambioGuardia.id != exclude if exclude is not None else db.true(),
            CambioGuardiaCupo.anio_imputacion == following_period.year,
            CambioGuardiaCupo.mes_imputacion == following_period.month,
            CambioGuardiaCupo.uso_anticipado.is_(True)))
        aliases = {name_key(name)} if name else set()
        if employee_id:
            from app.models.employees import Funcionario
            employee = db.session.get(Funcionario, employee_id)
            if employee:
                aliases.add(name_key(employee.nombre_completo))
        for allocation in rows:
            if allocation.tipo_cupo in advance_used and _matches_employee(allocation, name, employee_id, aliases):
                advance_used[allocation.tipo_cupo] += 1
    return {
        'mes': current_period.strftime('%m/%Y'),
        'mes_siguiente': following_period.strftime('%m/%Y'),
        'usados': current,
        'limites': dict(LIMITS),
        'disponibles': {kind: max(0, LIMITS[kind] - current[kind]) for kind in LIMITS},
        'anticipados': advance_used,
        'usados_mes_siguiente': following,
        'disponibles_mes_siguiente': {kind: max(0, LIMITS[kind] - following[kind]) for kind in LIMITS},
    }


def _consumers(values):
    kind = values['tipo_cambio']
    if kind not in QUOTA_ROLES:
        return []
    return [(role, values[role], values.get(role + '_funcionario_id')) for role in QUOTA_ROLES[kind]]


def plan_monthly_allocations(values, reference_day, exclude=None, roles=None):
    kind = values['tipo_cambio']
    if kind not in LIMITS:
        return []
    plans = []
    for role, name, employee_id in _consumers(values):
        if roles is not None and role not in roles:
            continue
        current_period = date(reference_day.year, reference_day.month, 1)
        used = monthly_usage(name, employee_id, current_period, exclude)[kind]
        if used < LIMITS[kind]:
            period, advanced = current_period, False
        elif reference_day.day >= 16:
            if not _allocation_table_exists():
                raise GuardiaValidation('No se puede anticipar cupo hasta completar la migración del control mensual.')
            period = next_month(current_period)
            following_used = monthly_usage(name, employee_id, period, exclude)[kind]
            if following_used >= LIMITS[kind]:
                raise GuardiaValidation('No existen cupos disponibles para el mes actual ni para el mes siguiente.')
            advanced = True
        else:
            month_name = MONTH_NAMES[current_period.month - 1]
            raise GuardiaValidation(f'{name} ha agotado sus cambios de guardia correspondientes a {month_name} de {current_period.year}.')
        plans.append({
            'funcionario_id': int(employee_id) if employee_id else None,
            'funcionario_nombre': name,
            'participante': 'S' if role == 'solicitante' else 'R',
            'tipo_cupo': kind,
            'fecha_referencia': reference_day,
            'anio_imputacion': period.year,
            'mes_imputacion': period.month,
            'uso_anticipado': advanced,
        })
    return plans


def save_monthly_allocations(record_id, plans, user_id):
    if not _allocation_table_exists():
        return
    for plan in plans:
        db.session.add(CambioGuardiaCupo(cambio_guardia_id=record_id,
            usuario_registro_id=user_id, **plan))


def sync_monthly_allocations(record, values, user_id, confirmed_advance=False):
    if not _allocation_table_exists() or record.tipo_cambio not in LIMITS:
        return
    existing = {row.participante: row for row in db.session.scalars(
        db.select(CambioGuardiaCupo).where(CambioGuardiaCupo.cambio_guardia_id == record.id)
    )}
    wanted = {('S' if role == 'solicitante' else 'R'): (role, name, employee_id)
              for role, name, employee_id in _consumers(values)}
    changed = {}
    for participant, (role, name, employee_id) in wanted.items():
        allocation = existing.get(participant)
        unchanged = allocation and (
            (allocation.funcionario_id == int(employee_id) if allocation.funcionario_id and employee_id
             else allocation.funcionario_id is None and not employee_id and _name_matches(allocation.funcionario_nombre, name))
        )
        if not unchanged:
            changed[role] = (name, employee_id)
    if not changed:
        return
    plans = plan_monthly_allocations(values, record.fecha_cambio, exclude=record.id, roles=set(changed))
    require_advance_confirmation(plans, confirmed_advance)
    for participant in ('S', 'R'):
        allocation = existing.get(participant)
        role = 'solicitante' if participant == 'S' else 'reemplazante'
        if role in changed:
            if allocation:
                plan = next(item for item in plans if item['participante'] == participant)
                previous = {'funcionario_id': allocation.funcionario_id,
                    'funcionario_nombre': allocation.funcionario_nombre,
                    'anio_imputacion': allocation.anio_imputacion,
                    'mes_imputacion': allocation.mes_imputacion,
                    'uso_anticipado': allocation.uso_anticipado}
                for key, value in plan.items():
                    setattr(allocation, key, value)
                allocation.usuario_modificacion_id = user_id
                allocation.fecha_modificacion = utcnow()
                from app.hospital_services.classification import audit
                audit('CUPO_GUARDIA_REASIGNADO', 'cupos_cambios_guardia', allocation.id,
                    details={'anterior': previous, 'nuevo': {
                        'funcionario_id': allocation.funcionario_id,
                        'funcionario_nombre': allocation.funcionario_nombre,
                        'anio_imputacion': allocation.anio_imputacion,
                        'mes_imputacion': allocation.mes_imputacion,
                        'uso_anticipado': allocation.uso_anticipado}}, user_id=user_id)
            else:
                plan = next(item for item in plans if item['participante'] == participant)
                db.session.add(CambioGuardiaCupo(cambio_guardia_id=record.id,
                    usuario_registro_id=user_id, **plan))
        elif participant not in wanted and allocation:
            db.session.delete(allocation)


def check_restored_allocations(record):
    if not _allocation_table_exists():
        return
    allocations = db.session.scalars(db.select(CambioGuardiaCupo).where(
        CambioGuardiaCupo.cambio_guardia_id == record.id))
    for allocation in allocations:
        used = _allocation_usage(allocation.funcionario_nombre, allocation.funcionario_id,
            date(allocation.anio_imputacion, allocation.mes_imputacion, 1), exclude=record.id)[allocation.tipo_cupo]
        if used >= LIMITS[allocation.tipo_cupo]:
            raise GuardiaValidation(f'No se puede restaurar: {allocation.funcionario_nombre} ya no tiene cupo disponible en {allocation.mes_imputacion:02d}/{allocation.anio_imputacion}.')


def record_values(record):
    return {key: getattr(record, key) for key in ('tipo_cambio', 'solicitante', 'reemplazante',
        'solicitante_funcionario_id', 'reemplazante_funcionario_id')}


def validate_new_kind(values, details, record=None):
    kind = values['tipo_cambio']
    if kind not in ('REEMPLAZO', 'EMERGENCIA', 'PAGADA'):
        return
    if kind == 'PAGADA' and not _allocation_table_exists():
        return
    from app.models.employees import Funcionario
    for role, name, employee_id in _consumers(values):
        if not employee_id:
            raise GuardiaValidation('Busca y selecciona la ficha del funcionario para controlar sus cupos individuales.')
        person = db.session.get(Funcionario, employee_id)
        preserved = bool(person and record and getattr(record, role + '_funcionario_id') == person.id
                         and getattr(record, role) == name)
        if not person or (_name_matches(person.nombre_completo, name) is False and not preserved):
            raise GuardiaValidation('El nombre debe coincidir con la ficha seleccionada.')
    if kind == 'PAGADA':
        return
    if not values.get('solicitante_funcionario_id') or not values.get('reemplazante_funcionario_id'):
        raise GuardiaValidation('Busca y selecciona las fichas de ambos participantes para controlar sus cupos individuales.')
    if values['solicitante_funcionario_id'] == values['reemplazante_funcionario_id']:
        raise GuardiaValidation('El solicitante y el reemplazante deben ser personas distintas.')
    for row in details:
        from datetime import time
        if not row['fecha_guardia'] or (row['hora_inicio'], row['hora_fin']) not in (
                (time(6), time(12)), (time(12), time(18)), (time(18), time(6)), (time(6), time(18))):
            raise GuardiaValidation('Usa mañana 06:00–12:00, tarde 12:00–18:00, noche 18:00–06:00 o guardia de 12 horas 06:00–18:00 en fin de semana.')
        if (row['hora_inicio'], row['hora_fin']) == (time(6), time(18)) and row['fecha_guardia'].weekday() < 5:
            raise GuardiaValidation('La guardia diurna de 12 horas corresponde a fines de semana.')
    if kind != 'REEMPLAZO':
        return
    if len(details) != 4 or [(d['participante'], d['codigo']) for d in details] != [('S', 'L'), ('R', 'G'), ('R', 'L'), ('S', 'G')]:
        raise GuardiaValidation('El intercambio debe contener las cuatro asignaciones: solicitante L, reemplazante G, reemplazante L y solicitante G.')
    def shift(row):
        return tuple(row[k] for k in ('fecha_guardia', 'hora_inicio', 'hora_fin'))
    if shift(details[0]) != shift(details[1]) or shift(details[2]) != shift(details[3]) or shift(details[0]) == shift(details[2]):
        raise GuardiaValidation('Cada guardia debe tener una persona libre y otra cubriendo el mismo horario. Las dos guardias del intercambio deben ser distintas.')


def check_duplicate(values, details, exclude=None):
    if values['tipo_cambio'] != 'REEMPLAZO':
        return
    expected = sorted((values['solicitante_funcionario_id'] if d['participante'] == 'S' else values['reemplazante_funcionario_id'],
        d['fecha_guardia'], d['hora_inicio'], d['hora_fin'], d['codigo']) for d in details)
    query = db.select(CambioGuardia).where(CambioGuardia.tipo_cambio == 'REEMPLAZO',
        CambioGuardia.eliminado.is_(False), CambioGuardia.id != exclude if exclude else db.true(),
        CambioGuardia.solicitante_funcionario_id.in_((values['solicitante_funcionario_id'], values['reemplazante_funcionario_id'])),
        CambioGuardia.reemplazante_funcionario_id.in_((values['solicitante_funcionario_id'], values['reemplazante_funcionario_id'])))
    for row in db.session.scalars(query):
        actual = sorted((row.solicitante_funcionario_id if d.participante == 'S' else row.reemplazante_funcionario_id,
            d.fecha_guardia, d.hora_inicio, d.hora_fin, d.codigo) for d in row.detalles)
        if actual == expected:
            raise GuardiaValidation('Este intercambio ya está registrado. Consulta el registro existente para evitar duplicarlo.')
