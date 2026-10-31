"""Cupos calculados desde operaciones vigentes; sin reinicios ni historial paralelo."""
from datetime import date, time
from app.extensions import db
from app.models.administration import CambioGuardia
from app.administration.forms import name_key

LIMITS = {'REEMPLAZO': 2, 'PAGADA': 1, 'EMERGENCIA': 1}
LABELS = {'REEMPLAZO': 'con reemplazante', 'PAGADA': 'pagados', 'EMERGENCIA': 'de emergencia'}


class GuardiaValidation(ValueError):
    pass


def lock_monthly():
    # Mismo bloqueo en altas, ediciones y restauraciones, hasta COMMIT/ROLLBACK.
    # Orden único: cupos antes de bloquear filas o adjuntos.
    db.session.execute(db.text('SELECT pg_advisory_xact_lock(901,12)'))


def monthly_usage(name, employee_id, day, exclude=None):
    start = day.replace(day=1)
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    rows = db.session.scalars(db.select(CambioGuardia).where(
        CambioGuardia.eliminado.is_(False), CambioGuardia.fecha_cambio >= start,
        CambioGuardia.fecha_cambio < end, CambioGuardia.tipo_cambio.in_(LIMITS),
        CambioGuardia.id != exclude if exclude is not None else db.true()))
    # Una ficha mantiene su identidad aunque cambie de nombre. Para históricos
    # sin ficha se compara el nombre normalizado, sin modificar esas filas.
    aliases = {name_key(name)}
    if employee_id:
        from app.models.employees import Funcionario
        person = db.session.get(Funcionario, employee_id)
        if person:
            aliases.add(name_key(person.nombre_completo))
    result = dict.fromkeys(LIMITS, 0)
    for row in rows:
        roles = ('solicitante', 'reemplazante') if row.tipo_cambio == 'REEMPLAZO' else ('solicitante',)
        for role in roles:
            linked = getattr(row, role + '_funcionario_id')
            matches = (linked == employee_id if linked and employee_id else name_key(getattr(row, role)) in aliases)
            if matches:
                result[row.tipo_cambio] += 1
                break
    return result


def check_monthly(values, day, exclude=None):
    kind = values['tipo_cambio']
    if kind not in LIMITS:
        return
    roles = ('solicitante', 'reemplazante') if kind == 'REEMPLAZO' else ('solicitante',)
    for role in roles:
        used = monthly_usage(values[role], values.get(role + '_funcionario_id'), day, exclude)[kind]
        if used >= LIMITS[kind]:
            raise GuardiaValidation(f"{values[role]} ya alcanzó el límite mensual de cambios {LABELS[kind]} "
                f"({used} de {LIMITS[kind]}) en {day:%m/%Y}. No es posible registrar otro cambio de este tipo durante este mes.")


def record_values(record):
    return {key: getattr(record, key) for key in ('tipo_cambio', 'solicitante', 'reemplazante',
        'solicitante_funcionario_id', 'reemplazante_funcionario_id')}


def validate_new_kind(values, details, record=None):
    if values['tipo_cambio'] not in ('REEMPLAZO', 'EMERGENCIA'):
        return
    if not values.get('solicitante_funcionario_id') or not values.get('reemplazante_funcionario_id'):
        raise GuardiaValidation('Busca y selecciona las fichas de ambos participantes para controlar sus cupos individuales.')
    if values['solicitante_funcionario_id'] == values['reemplazante_funcionario_id']:
        raise GuardiaValidation('El solicitante y el reemplazante deben ser personas distintas.')
    from app.models.employees import Funcionario
    for role in ('solicitante', 'reemplazante'):
        person = db.session.get(Funcionario, values[role + '_funcionario_id'])
        preserved = bool(person and record and getattr(record, role + '_funcionario_id') == person.id
                         and getattr(record, role) == values[role])
        if not person or (name_key(person.nombre_completo) != name_key(values[role]) and not preserved):
            raise GuardiaValidation('El nombre debe coincidir con la ficha seleccionada.')
    for row in details:
        if not row['fecha_guardia'] or (row['hora_inicio'], row['hora_fin']) not in (
                (time(6), time(12)), (time(12), time(18)), (time(18), time(6)), (time(6), time(18))):
            raise GuardiaValidation('Usa mañana 06:00–12:00, tarde 12:00–18:00, noche 18:00–06:00 o guardia de 12 horas 06:00–18:00 en fin de semana.')
        if (row['hora_inicio'], row['hora_fin']) == (time(6), time(18)) and row['fecha_guardia'].weekday() < 5:
            raise GuardiaValidation('La guardia diurna de 12 horas corresponde a fines de semana.')
    if values['tipo_cambio'] != 'REEMPLAZO':
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
