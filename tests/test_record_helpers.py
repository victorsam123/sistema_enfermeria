from datetime import date
from uuid import uuid4

from app.extensions import db
from app.models import Usuario
from app.models.employees import Funcionario


def employee_for_record(app, name, user_id=None):
    with app.app_context():
        if user_id is None:
            user_id = db.session.scalar(db.select(Usuario.id).where(Usuario.username == 'victor'))
        names, surname = name.rsplit(' ', 1)
        person = db.session.scalar(db.select(Funcionario).where(
            Funcionario.nombres == names, Funcionario.apellidos == surname))
        if person is None:
            from app.employees.services import create_employee
            person = create_employee({
                'nombres': names,
                'apellidos': surname,
                'cedula': str(1_000_000 + uuid4().int % 9_000_000),
                'carrera': 'LIC. EN ENFERMERIA',
                'fecha_nacimiento': date(1980, 1, 1),
                'fecha_ingreso': date(2020, 1, 1),
                'telefono': None,
                'direccion_actual': 'Domicilio de prueba',
                'servicio_id': 1,
            }, [], str(uuid4()), user_id)
        elif not any(link.activo for link in person.vinculos):
            from app.employees.employment_services import add_link
            add_link(person.id, date(2020, 1, 1), user_id, str(uuid4()))
        db.session.commit()
        return person.id


def associate_employee(app, values, model, key, user_id=None, employee_id=None):
    if model is Funcionario:
        return values
    if key == 'vacaciones':
        name, field = values['nombres_apellidos'], 'funcionario_id'
    elif key == 'pagadas':
        name, field = values['solicitante'], 'solicitante_funcionario_id'
    else:
        return values
    values = dict(values)
    if employee_id is None:
        employee_id = employee_for_record(app, name, user_id)
    else:
        with app.app_context():
            person = db.session.get(Funcionario, employee_id)
            if person is None or person.nombre_completo != name:
                raise AssertionError('La ficha del funcionario debe coincidir con el nombre enviado.')
    values[field] = str(employee_id)
    return values
