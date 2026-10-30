import re
from datetime import date
from uuid import uuid4
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.engine import make_url
from flask_migrate import upgrade
import pytest
from unittest.mock import patch
from app import create_app
from app.extensions import db
from app.models import Usuario, IntentoLogin, LogAcceso
from app.models.user_audit import AuditoriaUsuario
from app.models.administration import Justificativo, CambioGuardia, DetalleCambioGuardia
from app.models.leave_records import Vacacion, Comisionado
from app.models.reposos import Reposo
from app.models.hospital_services import HistorialAdministrativo, Servicio
from app.security.permissions import ROLE_LABELS
from test_auth import login
from test_administration import JUST_DATA, GUARD_DATA, form_values
from test_leave_records import VAC_DATA, COM_DATA
from test_reposos import DATA as REST_DATA
from test_service_files_reports import report, workbook

PASSWORD = 'AccesoInicial2026!'
NEW_PASSWORD = 'CambioSeguro2027!'
PATHS = [('/justificativos/', JUST_DATA, Justificativo, 'justificativos'),
    ('/reposo/', REST_DATA, Reposo, 'reposos'),
    ('/reposo/cambio-guardia/', GUARD_DATA, CambioGuardia, 'guardias'),
    ('/reposo/cambio-guardia-pagada/', GUARD_DATA, CambioGuardia, 'pagadas'),
    ('/vacaciones/', VAC_DATA, Vacacion, 'vacaciones'),
    ('/comisionados/', COM_DATA, Comisionado, 'comisionados')]


@pytest.fixture(scope='module')
def accounts(app):
    result = {}
    common_hash = generate_password_hash(PASSWORD, method='scrypt')
    with app.app_context():
        for role in ROLE_LABELS:
            username = 'seg8_' + role.lower()
            user = db.session.scalar(db.select(Usuario).where(Usuario.username == username))
            if user is None:
                user = Usuario(username=username, nombre='Prueba ' + role, rol=role, activo=True, protegido=False,
                    debe_cambiar_password=False, password_hash=common_hash)
                db.session.add(user)
            db.session.flush()
            result[role] = (user.id, username)
        db.session.commit()
    return result, common_hash


@pytest.fixture(autouse=True)
def clean_records(app, accounts):
    mapping, common_hash = accounts
    with app.app_context():
        for model in (HistorialAdministrativo, AuditoriaUsuario, DetalleCambioGuardia, CambioGuardia, Justificativo, Reposo, Vacacion, Comisionado):
            db.session.execute(db.delete(model))
        for role, (uid, _) in mapping.items():
            user = db.session.get(Usuario, uid)
            user.rol, user.activo, user.debe_cambiar_password, user.password_hash = role, True, False, common_hash
        db.session.commit()
    yield
    with app.app_context():
        db.session.rollback()
        db.session.remove()


def client_for(app, accounts, role):
    client = app.test_client()
    username = accounts[0][role][1]
    assert login(client, username, PASSWORD).status_code == 302
    return client


def form_fields(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    values = {}
    for key in ('csrf_token', 'version'):
        match = re.search(r'name="' + key + r'"[^>]*value="([^"]*)"', response.text)
        if match:
            values[key] = match.group(1)
    return values


def clear_limits(app):
    with app.app_context():
        db.session.execute(db.delete(IntentoLogin))
        db.session.commit()


@pytest.mark.parametrize('role', ROLE_LABELS)
def test_dashboard_and_menus_follow_role(app, accounts, role):
    client = client_for(app, accounts, role)
    html = client.get('/').text
    assert ROLE_LABELS[role] in html
    assert 'Cuenta permanente protegida' not in html
    for name in ('Justificativo', 'Reposo', 'Cambio de Guardia', 'Vacaciones', 'Comisionados'):
        assert name in html
    administrative = role in ('SUPERADMIN', 'JEFATURA')
    for link in ('/usuarios/', '/informes/', '/archivos-por-servicio/'):
        assert (f'href="{link}"' in html) == administrative
    assert ('href="/configuracion/servicios/"' in html) == (role == 'SUPERADMIN')
    assert ('href="/registros/eliminados"' in html) == (role == 'SUPERADMIN')


@pytest.mark.parametrize('role', ROLE_LABELS)
@pytest.mark.parametrize('path,data,model,key', PATHS)
def test_all_roles_create_but_loading_roles_never_get_history(app, accounts, role, path, data, model, key):
    privileged = client_for(app, accounts, 'SUPERADMIN')
    secret = {**data, 'servicio_id': '7'}
    if model is CambioGuardia:
        secret['solicitante'] = 'Secreto Anterior Funcionario'
    else:
        secret['nombres_apellidos'] = 'Secreto Anterior Funcionario'
    assert privileged.post(path, data=form_values(privileged, path, secret)).status_code == 303
    clear_limits(app)
    client = client_for(app, accounts, role)
    page = client.get(path)
    if role in ('OPERADOR', 'SUPERVISOR'):
        assert 'Secreto Anterior Funcionario' not in page.text
        assert 'id="registros"' not in page.text and 'VER REGISTROS' not in page.text
        for forbidden in ('>Editar', '>Eliminar', '>Imprimir', '/informes/', '/archivos-por-servicio/', '/usuarios/'):
            assert forbidden not in page.text
    result = client.post(path, data=form_values(client, path, data), follow_redirects=True)
    assert result.status_code == 200
    if role in ('OPERADOR', 'SUPERVISOR'):
        assert 'Código del registro:' in result.text
        assert 'id="registros"' not in result.text
    with app.app_context():
        record = db.session.scalar(db.select(model).where(model.usuario_registro_id == accounts[0][role][0]).order_by(model.id.desc()))
        assert record and record.servicio_id == 1 and not record.eliminado
        assert db.session.scalar(db.select(HistorialAdministrativo).where(HistorialAdministrativo.evento == 'REGISTRO_CREADO',
            HistorialAdministrativo.entidad == model.__tablename__, HistorialAdministrativo.registro_id == record.id))
    if role in ('OPERADOR', 'SUPERVISOR'):
        assert client.get(path + str(record.id) + '/editar').status_code == 403
        denied = client.post(f'/registros/{key}/{record.id}/eliminar', data={'csrf_token': form_fields(client, path)['csrf_token'],
            'version': str(record.version), 'motivo': 'Intento prohibido', 'confirmacion': 'CONFIRMAR'})
        assert denied.status_code == 403 and 'No tiene permisos para realizar esta operación' in denied.text
        assert client.get(f'/registros/{key}/{record.id}/imprimir').status_code == 403
        assert client.get('/informes/').status_code == 403
        assert client.post('/informes/', data={'csrf_token': form_fields(client, path)['csrf_token'],
            'desde': '01/10/2026', 'hasta': '30/10/2026', 'categoria': 'completo', 'servicio_id': '1', 'accion': 'descargar'}).status_code == 403
        with app.app_context():
            assert not db.session.get(model, record.id).eliminado


def test_superadmin_creates_users_with_canonical_roles_hash_and_first_access(app, accounts):
    admin = client_for(app, accounts, 'SUPERADMIN')
    username = 'alta8_' + uuid4().hex[:12]
    values = {**form_fields(admin, '/usuarios/nuevo'), 'nombre': 'Funcionario Prueba Alta', 'username': username,
        'rol': 'JEFATURA', 'activo': '1', 'password': PASSWORD, 'confirm_password': PASSWORD}
    assert admin.post('/usuarios/nuevo', data=values).status_code == 303
    with app.app_context():
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == username))
        uid = user.id
        assert user.rol == 'JEFATURA' and user.debe_cambiar_password and user.check_password(PASSWORD)
        assert user.password_hash != PASSWORD
        assert db.session.scalar(db.select(AuditoriaUsuario).where(AuditoriaUsuario.usuario_afectado_id == uid)).accion == 'USUARIO_CREADO'
    duplicate = admin.post('/usuarios/nuevo', data={**values, 'username': username.upper()})
    assert duplicate.status_code == 409
    assert PASSWORD not in duplicate.text
    newcomer = app.test_client()
    assert login(newcomer, username, PASSWORD).status_code == 302
    assert newcomer.get('/').location.endswith('/mi-cuenta/cambiar-password')
    assert newcomer.get('/informes/').status_code == 303
    form = form_fields(newcomer, '/mi-cuenta/cambiar-password')
    assert newcomer.post('/justificativos/', data={**JUST_DATA, 'csrf_token': form['csrf_token'], 'servicio_id': '1', 'solicitud_id': str(uuid4())}).status_code == 303
    bad = newcomer.post('/mi-cuenta/cambiar-password', data={**form, 'actual': 'incorrecta', 'password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    assert bad.status_code == 422
    clear_limits(app)
    changed = newcomer.post('/mi-cuenta/cambiar-password', data={**form, 'actual': PASSWORD, 'password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    assert changed.status_code == 303
    assert newcomer.get('/').status_code == 200
    with app.app_context():
        user = db.session.get(Usuario, uid)
        assert not user.debe_cambiar_password and user.check_password(NEW_PASSWORD)
        assert db.session.scalar(db.select(db.func.count()).select_from(Justificativo)) == 0
        descriptions = db.session.scalars(db.select(AuditoriaUsuario.descripcion)).all()
        assert all(PASSWORD not in text and NEW_PASSWORD not in text for text in descriptions)


@pytest.mark.parametrize('role', ['OPERADOR', 'SUPERVISOR'])
def test_jefatura_can_only_manage_loading_roles(app, accounts, role):
    client = client_for(app, accounts, 'JEFATURA')
    html = client.get('/usuarios/nuevo').text
    assert 'value="SUPERADMIN"' not in html and 'value="JEFATURA"' not in html
    username = 'jef_alta8_' + uuid4().hex[:10]
    data = {**form_fields(client, '/usuarios/nuevo'), 'nombre': 'Cuenta creada por Jefatura', 'username': username,
        'rol': role, 'activo': '1', 'password': PASSWORD, 'confirm_password': PASSWORD}
    assert client.post('/usuarios/nuevo', data=data).status_code == 303
    for high_role in ('SUPERADMIN', 'JEFATURA'):
        assert client.post('/usuarios/nuevo', data={**data, 'username': 'ataque8_' + uuid4().hex[:8], 'rol': high_role}).status_code == 403
    for protected_id in (accounts[0]['SUPERADMIN'][0], accounts[0]['JEFATURA'][0], 1):
        for action in ('editar', 'password', 'estado'):
            path = f'/usuarios/{protected_id}/{action}'
            assert client.get(path).status_code == 403
            assert client.post(path, data=data).status_code == 403
        assert client.get(f'/usuarios/{protected_id}/actividad').status_code == 403
    assert client.get('/configuracion/servicios/').status_code == 403
    assert client.get('/configuracion/servicios/historial').status_code == 200


def test_edit_roles_reset_and_account_state_invalidate_existing_sessions(app, accounts):
    admin = client_for(app, accounts, 'SUPERADMIN')
    operator = client_for(app, accounts, 'OPERADOR')
    uid, username = accounts[0]['OPERADOR']
    edit = f'/usuarios/{uid}/editar'
    data = {**form_fields(admin, edit), 'nombre': 'Operador con nuevo rol', 'username': username,
        'rol': 'SUPERVISOR', 'activo': '1'}
    assert admin.post(edit, data=data).status_code == 303
    assert operator.get('/').status_code == 302
    assert admin.post(edit, data=data).status_code == 409
    clear_limits(app)
    operator = client_for(app, accounts, 'OPERADOR')
    # La cuenta conserva su nombre de acceso pero ya tiene rol SUPERVISOR.
    assert 'Supervisor' in operator.get('/').text
    path = f'/usuarios/{uid}/password'
    reset = {**form_fields(admin, path), 'password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD}
    assert admin.post(path, data=reset).status_code == 303
    assert operator.get('/').status_code == 302
    clear_limits(app)
    temporary = app.test_client()
    assert login(temporary, username, NEW_PASSWORD).status_code == 302
    assert temporary.get('/').status_code == 303
    state_path = f'/usuarios/{uid}/estado'
    fields = form_fields(admin, state_path)
    assert admin.post(state_path, data={**fields, 'confirmacion': 'CONFIRMAR'}).status_code == 303
    assert temporary.get('/').status_code == 302
    fields = form_fields(admin, state_path)
    assert admin.post(state_path, data={**fields, 'confirmacion': 'CONFIRMAR'}).status_code == 303
    assert temporary.get('/').status_code == 302  # Reactivar no revive una sesión anterior.
    with app.app_context():
        actions = set(db.session.scalars(db.select(AuditoriaUsuario.accion).where(AuditoriaUsuario.usuario_afectado_id == uid)))
        assert {'ROL_CAMBIADO', 'PASSWORD_RESTABLECIDO', 'USUARIO_DESACTIVADO', 'USUARIO_ACTIVADO'} <= actions


@pytest.mark.parametrize('bad_password,confirm', [('123456', '123456'), ('solominusculas123', 'solominusculas123'),
    ('SINMINUSCULAS123', 'SINMINUSCULAS123'), ('FaltanNumeros!', 'FaltanNumeros!'), (PASSWORD, 'Distinta2026!')])
def test_password_policy_and_confirmation(app, accounts, bad_password, confirm):
    admin = client_for(app, accounts, 'SUPERADMIN')
    data = {**form_fields(admin, '/usuarios/nuevo'), 'nombre': 'Usuario validación', 'username': 'valid8_' + uuid4().hex[:10],
        'rol': 'OPERADOR', 'activo': '1', 'password': bad_password, 'confirm_password': confirm}
    assert admin.post('/usuarios/nuevo', data=data).status_code == 422


@pytest.mark.parametrize('role', ['SUPERADMIN', 'JEFATURA'])
@pytest.mark.parametrize('path,values,model,key', PATHS)
def test_admin_roles_edit_delete_without_physical_loss_and_superadmin_restore(app, accounts, role, path, values, model, key):
    admin = client_for(app, accounts, role)
    assert admin.post(path, data=form_values(admin, path, values)).status_code == 303
    with app.app_context():
        record = db.session.scalar(db.select(model))
        rid, creator, created = record.id, record.usuario_registro_id, record.fecha_creacion
        details_ids = [d.id for d in record.detalles] if model is CambioGuardia else []
        if model is CambioGuardia:
            details = [dict(detalle_id=str(d.id), participante=d.participante, fecha_guardia=d.fecha_guardia.strftime('%d/%m/%Y'),
                hora_inicio=d.hora_inicio.strftime('%H:%M'), hora_fin=d.hora_fin.strftime('%H:%M'), codigo=d.codigo or '') for d in record.detalles]
    edit_path = path + str(rid) + '/editar'
    if model is CambioGuardia:
        from test_guardias_multifecha import form_data
        update = form_data(admin, edit_path, names={'solicitante': 'Solicitante editado', 'reemplazante': values['reemplazante']}, details=details)
    else:
        update = form_values(admin, edit_path, {**values, 'nombres_apellidos': 'Funcionario editado autorizado'})
    assert admin.post(edit_path, data=update).status_code == 303
    assert admin.get(f'/registros/{key}/{rid}/imprimir').status_code == 200
    assert admin.get(path + str(rid) + '/editar').status_code == 200
    delete_path = f'/registros/{key}/{rid}/eliminar'
    fields = form_fields(admin, delete_path)
    assert admin.post(delete_path, data={**fields, 'motivo': 'Corrección por registro duplicado', 'confirmacion': 'CONFIRMAR'}).status_code == 303
    assert admin.get(path + str(rid) + '/editar').status_code == 404
    assert admin.get(f'/registros/{key}/{rid}/imprimir').status_code == 404
    assert ('Secreto' not in admin.get(path).text)
    _, _, xlsx = workbook(report(admin, category=key))
    name = 'Solicitante editado' if model is CambioGuardia else 'Funcionario editado autorizado'
    assert name not in [v for sheet in xlsx.values() for v in sheet['cells'].values()]
    with app.app_context():
        record = db.session.get(model, rid)
        assert record.eliminado and record.usuario_eliminacion_id == accounts[0][role][0]
        assert record.fecha_eliminacion and record.motivo_eliminacion == 'Corrección por registro duplicado'
        assert (record.usuario_registro_id, record.fecha_creacion) == (creator, created)
        version = str(record.version)
        if details_ids:
            assert [d.id for d in record.detalles] == details_ids
    clear_limits(app)
    root = client_for(app, accounts, 'SUPERADMIN')
    html = root.get('/registros/eliminados?categoria=' + key)
    assert html.status_code == 200 and 'Corrección por registro duplicado' in html.text
    assert root.get(f'/registros/{key}/{rid}/eliminado').status_code == 200
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html.text).group(1)
    restore_path = f'/registros/{key}/{rid}/restaurar'
    if role == 'JEFATURA':
        assert admin.get('/registros/eliminados').status_code == 403
        assert admin.get(f'/registros/{key}/{rid}/eliminado').status_code == 403
        assert admin.post(restore_path, data={'csrf_token': fields['csrf_token'], 'version': version}).status_code == 403
    assert root.post(restore_path, data={'csrf_token': token, 'version': version}).status_code == 303
    assert root.get(path + str(rid) + '/editar').status_code == 200
    with app.app_context():
        assert not db.session.get(model, rid).eliminado
        events = set(db.session.scalars(db.select(HistorialAdministrativo.evento).where(
            HistorialAdministrativo.entidad == model.__tablename__, HistorialAdministrativo.registro_id == rid)))
        assert {'REGISTRO_CREADO', 'REGISTRO_MODIFICADO', 'REGISTRO_ELIMINADO', 'REGISTRO_RESTAURADO'} <= events


@pytest.mark.parametrize('role', ROLE_LABELS)
def test_protected_victor_cannot_be_managed_from_any_other_account(app, accounts, role):
    client = client_for(app, accounts, role)
    with app.app_context():
        victor = db.session.scalar(db.select(Usuario).where(Usuario.username == 'victor'))
        before = victor.id, victor.password_hash, victor.rol, victor.activo, victor.protegido
    csrf = form_fields(client, '/justificativos/')['csrf_token']
    for action in ('editar', 'password', 'estado'):
        assert client.get(f'/usuarios/{before[0]}/{action}').status_code == 403
        assert client.post(f'/usuarios/{before[0]}/{action}', data={'csrf_token': csrf, 'rol': 'OPERADOR', 'activo': '0',
            'nombre': 'Cambio prohibido', 'username': 'otro', 'password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD,
            'confirmacion': 'CONFIRMAR', 'version': '1'}).status_code == 403
    assert client.delete(f'/usuarios/{before[0]}', data={'csrf_token': csrf}).status_code in (404, 405)
    with app.app_context():
        victor = db.session.get(Usuario, before[0])
        assert (victor.id, victor.password_hash, victor.rol, victor.activo, victor.protegido) == before


def test_security_routes_require_csrf_and_queries_filter_users(app, accounts):
    admin = client_for(app, accounts, 'SUPERADMIN')
    uid = accounts[0]['OPERADOR'][0]
    for path in ('/usuarios/nuevo', f'/usuarios/{uid}/editar', f'/usuarios/{uid}/password', f'/usuarios/{uid}/estado', '/mi-cuenta/cambiar-password'):
        assert admin.post(path, data={}).status_code == 400
    html = admin.get('/usuarios/', query_string={'q': 'seg8_', 'rol': 'SUPERVISOR', 'estado': '1'}).text
    assert accounts[0]['SUPERVISOR'][1] in html and accounts[0]['OPERADOR'][1] not in html
    assert admin.get(f'/usuarios/{uid}/actividad').status_code == 200
    assert 'password_hash' not in admin.get('/usuarios/').text


def test_database_checks_roles_and_complete_soft_delete_metadata(app, accounts):
    with app.app_context():
        with pytest.raises(DBAPIError):
            db.session.execute(db.text('UPDATE usuarios SET rol=:role WHERE id=:id'), {'role': 'ROL_INVENTADO', 'id': accounts[0]['OPERADOR'][0]})
            db.session.commit()
        db.session.rollback()
        db.session.add(Justificativo(nombres_apellidos='Validación SQL', fecha_inasistencia=date(2026, 10, 1), motivo='Prueba SQL',
            servicio_id=1, usuario_registro_id=accounts[0]['OPERADOR'][0], solicitud_id=uuid4(), eliminado=True,
            usuario_eliminacion_id=accounts[0]['SUPERADMIN'][0], fecha_eliminacion=date(2026, 10, 1)))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_migration8_preserves_old_accounts_passwords_and_records(app):
    schema = 'migracion8_' + uuid4().hex
    with app.app_context():
        assert make_url(app.config['SQLALCHEMY_DATABASE_URI']).database.endswith('_test')
        db.session.execute(db.text('CREATE SCHEMA ' + schema))
        db.session.commit()
    isolated = create_app({'TESTING': True, 'SECRET_KEY': app.secret_key, 'SESSION_COOKIE_SECURE': False,
        'SQLALCHEMY_DATABASE_URI': app.config['SQLALCHEMY_DATABASE_URI'],
        'SQLALCHEMY_ENGINE_OPTIONS': {'connect_args': {'options': '-csearch_path=' + schema}}})
    with isolated.app_context():
        upgrade(revision='0006_servicios_e_informes')
        from legacy_migration_helpers import legacy_admin
        uid = legacy_admin()
        db.session.execute(db.text("""INSERT INTO justificativos(nombres_apellidos,fecha_inasistencia,motivo,servicio_id,usuario_registro_id,solicitud_id)
            VALUES ('Registro anterior','2026-10-01','Motivo anterior',1,:uid,:uuid)"""), {'uid': uid, 'uuid': uuid4()})
        db.session.commit()
        previous = db.session.execute(db.text('SELECT * FROM justificativos')).one()
        original = db.session.execute(db.text("SELECT id,nombre,username,password_hash,activo,protegido FROM usuarios WHERE username='victor'")).one()
        db.session.remove()
        upgrade()
        current = db.session.execute(db.text('SELECT * FROM justificativos')).one()
        assert current[:len(previous)] == previous
        user = db.session.get(Usuario, uid)
        assert (user.id, user.nombre, user.username, user.password_hash, user.activo, user.protegido) == original
        assert user.rol == 'SUPERADMIN' and not user.debe_cambiar_password
        assert not db.session.scalar(db.select(Justificativo)).eliminado
        with pytest.raises(DBAPIError):
            db.session.execute(db.text("UPDATE usuarios SET activo=false WHERE username='victor'"))
        db.session.rollback()


def test_password_reset_during_login_cannot_adopt_new_session_credentials(app, accounts):
    from flask_login import login_user as real_login_user
    uid, username = accounts[0]['OPERADOR']
    replacement_hash = generate_password_hash(NEW_PASSWORD, method='scrypt')
    client = app.test_client()

    def race(user, **kwargs):
        # Representa un restablecimiento después de verificar la contraseña,
        # antes de firmar la cookie. No debe adoptar el nuevo sesion_version.
        with db.engine.begin() as connection:
            connection.execute(Usuario.__table__.update().where(Usuario.id == uid).values(password_hash=replacement_hash, debe_cambiar_password=True))
        return real_login_user(user, **kwargs)

    with patch('app.routes.auth.login_user', side_effect=race):
        assert login(client, username, PASSWORD).status_code == 302
    assert client.get('/').status_code == 302


def test_inactive_new_user_cannot_login_and_user_audit_has_no_secrets(app, accounts):
    admin = client_for(app, accounts, 'SUPERADMIN')
    username = 'inactivo8_' + uuid4().hex[:8]
    data = {**form_fields(admin, '/usuarios/nuevo'), 'nombre': 'Cuenta inicialmente inactiva',
        'username': username, 'rol': 'OPERADOR', 'activo': '0', 'password': PASSWORD, 'confirm_password': PASSWORD}
    assert admin.post('/usuarios/nuevo', data=data).status_code == 303
    client = app.test_client()
    assert login(client, username, PASSWORD).status_code == 401
    with app.app_context():
        assert all(PASSWORD not in e.descripcion for e in db.session.scalars(db.select(AuditoriaUsuario)))


def test_reset_during_own_password_change_does_not_revalidate_the_old_session(app, accounts):
    from flask_login import login_user as real_login_user
    uid = accounts[0]['OPERADOR'][0]
    client = client_for(app, accounts, 'OPERADOR')
    fields = form_fields(client, '/mi-cuenta/cambiar-password')
    replacement = generate_password_hash('RestablecimientoDistinto2028!', method='scrypt')

    def race(user, **kwargs):
        with db.engine.begin() as connection:
            connection.execute(Usuario.__table__.update().where(Usuario.id == uid).values(password_hash=replacement, debe_cambiar_password=True))
        return real_login_user(user, **kwargs)

    with patch('app.security.first_access.login_user', side_effect=race):
        response = client.post('/mi-cuenta/cambiar-password', data={**fields, 'actual': PASSWORD,
            'password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
        assert response.status_code == 303
    assert client.get('/').status_code == 302


def test_soft_delete_confirmation_csrf_and_stale_version(app, accounts):
    admin = client_for(app, accounts, 'SUPERADMIN')
    assert admin.post('/justificativos/', data=form_values(admin, '/justificativos/', JUST_DATA)).status_code == 303
    with app.app_context():
        row = db.session.scalar(db.select(Justificativo))
        rid = row.id
    path = f'/registros/justificativos/{rid}/eliminar'
    fields = form_fields(admin, path)
    assert admin.post(path, data={}).status_code == 400
    assert admin.post(path, data={**fields, 'motivo': 'No confirmado'}).status_code == 422
    changed = form_values(admin, f'/justificativos/{rid}/editar', {**JUST_DATA, 'motivo': 'Motivo actualizado'})
    assert admin.post(f'/justificativos/{rid}/editar', data=changed).status_code == 303
    assert admin.post(path, data={**fields, 'motivo': 'Intento obsoleto', 'confirmacion': 'CONFIRMAR'}).status_code == 409
    with app.app_context():
        assert not db.session.get(Justificativo, rid).eliminado
