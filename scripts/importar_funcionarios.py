"""Importa funcionarios desde la hoja de respuestas del formulario de actualización.

Uso (desde la raíz del proyecto, con DATABASE_URL configurada):
    python -m scripts.importar_funcionarios RESPUESTAS.csv            # simulación, no escribe
    python -m scripts.importar_funcionarios RESPUESTAS.csv --aplicar  # escribe

- Cédula repetida en la hoja: se usa solo la respuesta más reciente.
- Cédula inexistente en la base: se crea la ficha con sus vínculos laborales.
- Cédula existente: se actualizan los datos que no coinciden y los vínculos.
- Servicio sin equivalente en el catálogo: la fila no se importa y queda en el reporte.
"""
import argparse
import csv
import re
import sys
import unicodedata
from datetime import datetime
from uuid import uuid4
from app import create_app
from app.extensions import db
from app.models import Usuario, utcnow
from app.models.employees import Funcionario
from app.models.hospital_services import Servicio, PENDING_CODE
from app.employees.rules import normalize_cedula, paraguay_today
from app.employees.employment_services import add_link, update_link
from app.hospital_services.classification import audit, apply_service

COLS = {
    'name': 'Nombres y apellidos', 'cedula': 'Número de documento de identidad',
    'birth': 'Fecha de nacimiento', 'phone': 'Teléfono celular', 'city': 'Ciudad', 'hood': 'Barrio',
    'service': 'Servicio actual',
}
LINK_COLS = ('Fecha de ingreso a la institución (primer vínculo)',
             'Fecha de ingreso a la institución (segundo vínculo)',
             'Fecha de ingreso a la institución (tercer vínculo, si corresponde)',
             'Fecha de ingreso a la institución (cuarto vínculo, si corresponde)')

# (expresión sobre texto normalizado, código del catálogo). El orden importa.
SERVICE_RULES = (
    (r'\buti[ -]?p\b|\buti ninos?\b|\buti infantil\b|\buti pediatric|terapia (de |del )?(ninos?|infantil)|terapia intensiva pediatric|cuidados intensivos pediatric', 'UTI-P'),
    (r'\buti[ -]?a\b|\buti adulto|\buti\b|\buci\b|terapia intensiva|cuidados (intensivos|criticos)', 'UTI-A'),
    (r'neonatolog', 'NEONATOLOGIA'),
    (r'quirofano', 'QUIROFANO'),
    (r'maternidad|marernidad', 'MATERNIDAD'),
    (r'\bpai\b|p\.a\.i|programa ampliado|vacunacion', 'PAI'),
    (r'trauma', 'URGE-TRAUMA'),
    (r'supervision', 'SUPERVISION'),
    (r'pediatri\w* (internad|inter)', 'PEDIATRIA_INTER'),
    (r'urgenc\w* ?pediatri|urgecias pediatri|urgencia pediatric', 'PEDIATRIA_URGENCIA'),
    (r'\bcx\w*\b|cirugia', 'CIRUGIA'),
    (r'salud publica', 'SALUD_PUBLICA'),
    (r'laboratorio|\blab\b', 'LAB-UMT'),
)


def plain(text):
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r'\s+', ' ', text).strip()


def service_code(text, catalog_names):
    key = plain(text)
    if key in catalog_names:
        return catalog_names[key]
    for pattern, code in SERVICE_RULES:
        if re.search(pattern, key):
            return code
    return None


def clean_cedula(value):
    return re.sub(r'[\s.]+', '', value or '')


def parse_date(value):
    value = (value or '').strip()
    if not value:
        return None
    return datetime.strptime(value.split()[0], '%d/%m/%Y').date()


def split_name(full):
    words = full.split()
    if len(words) <= 2:
        return words[0], ' '.join(words[1:])
    half = len(words) // 2
    return ' '.join(words[:half]), ' '.join(words[half:])


def read_rows(path):
    with open(path, encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    latest, repeated = {}, set()
    for row in rows:
        try:
            key = normalize_cedula(clean_cedula(row[COLS['cedula']]))
        except ValueError:
            key = 'INVALIDA:' + (row[COLS['cedula']] or '').strip()
        if key in latest:
            repeated.add(key)
        latest[key] = row  # la hoja está en orden cronológico: gana la última
    return latest, repeated


def build(row, codes):
    cedula = normalize_cedula(clean_cedula(row[COLS['cedula']]))
    name = re.sub(r'\s+', ' ', row[COLS['name']]).strip()
    if not name:
        raise ValueError('nombre vacío')
    nombres, apellidos = split_name(name)
    if not apellidos:
        raise ValueError('falta apellido')
    birth = parse_date(row[COLS['birth']])
    links = [parse_date(row[c]) for c in LINK_COLS]
    links = [d for d in links if d]
    if not birth or not links:
        raise ValueError('falta fecha de nacimiento o de ingreso')
    today = paraguay_today()
    if birth > today or any(d > today or d < birth for d in links):
        raise ValueError('fechas incoherentes')
    phone = re.sub(r'\D', '', row[COLS['phone']] or '')
    phone = phone if 8 <= len(phone) <= 15 else None
    city = re.sub(r'\s+', ' ', row[COLS['city']]).strip()
    hood = re.sub(r'\s+', ' ', row[COLS['hood']]).strip()
    address = ', '.join(p for p in (hood, city) if p)[:500]
    if not address:
        raise ValueError('sin dirección')
    code = service_code(row[COLS['service']], codes['names'])
    if code is None or code not in codes['ids']:
        raise LookupError(row[COLS['service']].strip())
    return dict(cedula=cedula, name=name, nombres=nombres, apellidos=apellidos, birth=birth, links=links,
                phone=phone, address=address, servicio_id=codes['ids'][code])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('csv')
    parser.add_argument('--aplicar', action='store_true')
    parser.add_argument('--usuario', default='victor')
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == args.usuario))
        if user is None:
            sys.exit(f'No existe el usuario {args.usuario}.')
        services = db.session.scalars(db.select(Servicio).where(Servicio.activo.is_(True),
            Servicio.codigo != PENDING_CODE)).all()
        codes = {'ids': {s.codigo: s.id for s in services}, 'names': {plain(s.nombre): s.codigo for s in services}}
        latest, repeated = read_rows(args.csv)
        created = updated = unchanged = 0
        skipped, unmatched = [], {}
        for key, row in latest.items():
            try:
                data = build(row, codes)
            except LookupError as error:
                unmatched.setdefault(plain(str(error)), []).append(key)
                skipped.append((key, f'servicio sin equivalente: {error}'))
                continue
            except ValueError as error:
                skipped.append((key, str(error)))
                continue
            try:
                with db.session.begin_nested():
                    record = db.session.scalar(db.select(Funcionario).where(Funcionario.cedula == data['cedula'])
                        .with_for_update(of=Funcionario))
                    if record is None:
                        record = Funcionario(nombres=data['nombres'], apellidos=data['apellidos'], cedula=data['cedula'],
                            fecha_nacimiento=data['birth'], fecha_ingreso=data['links'][0], telefono=data['phone'],
                            direccion_actual=data['address'], servicio_id=data['servicio_id'],
                            cantidad_vinculos_declarada=len(data['links']),
                            usuario_registro_id=user.id, solicitud_id=uuid4())
                        db.session.add(record)
                        db.session.flush()
                        for entry in data['links']:
                            add_link(record.id, entry, user.id, uuid4())
                        audit('FUNCIONARIO_CREADO', 'funcionarios', record.id, user_id=user.id,
                              details={'origen': 'importacion_formulario'})
                        created += 1
                    else:
                        changed = []
                        if plain(record.nombre_completo) != plain(data['name']):
                            record.nombres, record.apellidos = data['nombres'], data['apellidos']
                            changed.append('nombre')
                        for field, value in (('fecha_nacimiento', data['birth']), ('telefono', data['phone']),
                                             ('direccion_actual', data['address'])):
                            if getattr(record, field) != value and (value is not None or field != 'telefono'):
                                setattr(record, field, value)
                                changed.append(field)
                        if record.servicio_id != data['servicio_id']:
                            apply_service(record, data['servicio_id'], user.id)
                            changed.append('servicio_id')
                        if record.cantidad_vinculos_declarada != len(data['links']):
                            record.cantidad_vinculos_declarada = len(data['links'])
                            changed.append('cantidad_vinculos_declarada')
                        db.session.flush()
                        current = {v.numero_vinculo: v for v in record.vinculos}
                        for number, entry in enumerate(data['links'], 1):
                            link = current.get(number)
                            if link is None:
                                add_link(record.id, entry, user.id, uuid4())
                                changed.append(f'vinculo_{number}')
                            elif link.fecha_ingreso != entry:
                                update_link(record.id, link.id, entry, link.version, user.id)
                                changed.append(f'vinculo_{number}')
                        if changed:
                            record.usuario_modificacion_id, record.fecha_modificacion = user.id, utcnow()
                            audit('FUNCIONARIO_MODIFICADO', 'funcionarios', record.id, user_id=user.id,
                                  details={'campos': changed, 'origen': 'importacion_formulario'})
                            db.session.flush()
                            updated += 1
                        else:
                            unchanged += 1
            except Exception as error:  # una fila inválida no detiene la carga
                skipped.append((key, f'error de base de datos: {str(error).splitlines()[0][:160]}'))
        if args.aplicar:
            db.session.commit()
        else:
            db.session.rollback()
        print(('APLICADO' if args.aplicar else 'SIMULACIÓN (no se escribió nada)') + f' | hoja: {len(latest)} cédulas únicas, '
              f'{len(repeated)} repetidas')
        print(f'  nuevos: {created} | actualizados: {updated} | sin cambios: {unchanged} | omitidos: {len(skipped)}')
        if unmatched:
            print('  servicios sin equivalente en el catálogo:')
            for name, ids in sorted(unmatched.items(), key=lambda item: -len(item[1])):
                print(f'    {len(ids):3d}  {name}')
        for key, reason in skipped:
            if not reason.startswith('servicio sin'):
                print(f'  omitido {key}: {reason}')


if __name__ == '__main__':
    main()
