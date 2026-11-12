from datetime import date, timedelta
from uuid import uuid4

from app.extensions import db
from app.models import Usuario
from app.models.employees import Funcionario
from app.models.hospital_services import Servicio
from app.models.leave_records import Vacacion
from tests.test_auth import login


def _create_employee(app, *, names, surname, birth_date, service, user_id):
    employee = Funcionario(
        nombres=names,
        apellidos=surname,
        cedula=str(100000000 + uuid4().int % 900000000),
        carrera='LIC. EN ENFERMERIA',
        fecha_nacimiento=birth_date,
        fecha_ingreso=max(birth_date, date(2020, 1, 1)),
        cantidad_vinculos=1,
        direccion_actual='Calle principal 123',
        servicio_id=service.id,
        usuario_registro_id=user_id,
        solicitud_id=uuid4(),
    )
    employee.usuario_modificacion_id = user_id
    return employee


def test_novedades_page_for_admin_and_permissions(app, client):
    with app.app_context():
        service = db.session.scalar(db.select(Servicio).where(Servicio.codigo == 'NEO_TEST_1'))
        if not service:
            service = Servicio(nombre='Neonatología', codigo='NEO_TEST_1')
        service_two = db.session.scalar(db.select(Servicio).where(Servicio.codigo == 'UTI_TEST_1'))
        if not service_two:
            service_two = Servicio(nombre='UTI - P', codigo='UTI_TEST_1')
        jefe = db.session.scalar(db.select(Usuario).where(Usuario.username == 'jefatura_test'))
        if not jefe:
            jefe = Usuario(nombre='Jefatura', username='jefatura_test', rol='JEFATURA', activo=True, protegido=False, debe_cambiar_password=False)
        operador = db.session.scalar(db.select(Usuario).where(Usuario.username == 'operador_test'))
        if not operador:
            operador = Usuario(nombre='Operador', username='operador_test', rol='OPERADOR', activo=True, protegido=False, debe_cambiar_password=False)
        jefe.set_password('clave-jefatura-test')
        operador.set_password('clave-operador-test')
        db.session.add_all([service, service_two, jefe, operador])
        db.session.commit()

        today = date.today()
        today_birthday = date(1980, today.month, today.day)
        tomorrow_day = today + timedelta(days=1)
        tomorrow_birthday = date(1980, tomorrow_day.month, tomorrow_day.day)
        upcoming_day = today + timedelta(days=5)
        upcoming_birthday = date(1980, upcoming_day.month, upcoming_day.day)
        far_day = today + timedelta(days=12)
        far_birthday = date(1980, far_day.month, far_day.day)
        employee_today = _create_employee(app, names='María', surname='González', birth_date=today_birthday, service=service, user_id=jefe.id)
        employee_tomorrow = _create_employee(app, names='Ana', surname='Benítez', birth_date=tomorrow_birthday, service=service, user_id=jefe.id)
        employee_upcoming = _create_employee(app, names='Juan', surname='Pérez', birth_date=upcoming_birthday, service=service_two, user_id=jefe.id)
        employee_far = _create_employee(app, names='Elena', surname='Ramírez', birth_date=far_birthday, service=service, user_id=jefe.id)
        db.session.add_all([employee_today, employee_tomorrow, employee_upcoming, employee_far])
        db.session.commit()

        holiday = Vacacion(
            nombres_apellidos='Pedro Martínez',
            funcionario_id=employee_upcoming.id,
            fecha_inicio=today + timedelta(days=2),
            fecha_termino=today + timedelta(days=6),
            total_dias=5,
            servicio_id=service_two.id,
            usuario_registro_id=jefe.id,
            usuario_modificacion_id=jefe.id,
            eliminado=False,
            solicitud_id=uuid4(),
        )
        db.session.add(holiday)
        db.session.commit()

    assert login(client).status_code == 302
    page = client.get('/novedades/')
    assert page.status_code == 200
    assert 'NOVEDADES DEL DEPARTAMENTO DE ENFERMERÍA' in page.text
    assert 'Cumpleaños del personal' in page.text
    assert 'María' in page.text
    assert 'Mañana cumpleaños' in page.text
    assert page.text.count('Ana Benítez') == 1
    assert 'Juan' in page.text
    assert 'Pedro Martínez' in page.text
    assert 'Servicio:</strong> Neonatología' not in page.text
    assert 'Hoy no se registran cumpleaños del personal' not in page.text

    assert login(client, 'operador_test', 'clave-operador-test').status_code == 302
    assert client.get('/novedades/').status_code == 403
