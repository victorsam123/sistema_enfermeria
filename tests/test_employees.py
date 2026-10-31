from datetime import date
from io import BytesIO
import json
import re
from uuid import uuid4
from unittest.mock import patch
import pytest
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app import create_app
from app.extensions import db
from app.models import Usuario, utcnow
from app.models.employees import Funcionario
from app.models.documents import DocumentoAdjunto
from app.models.administration import Justificativo, CambioGuardia, DetalleCambioGuardia
from app.models.reposos import Reposo
from app.models.leave_records import Vacacion, Comisionado
from app.models.hospital_services import HistorialAdministrativo, Servicio
from app.documents.storage import LocalStorage
from app.employees.rules import normalize_cedula, completed_age, seniority
from test_users_rbac import accounts, client_for, PATHS
from test_documents import fields, upload, photo
from test_auth import login

BASE = '/funcionarios/'
DATA = {'nombres': 'Ana María', 'apellidos': 'López Benítez', 'cedula': '1.234.567',
    'fecha_nacimiento': '15/05/1990', 'fecha_ingreso': '10/03/2015',
    'cantidad_vinculos': '2', 'direccion_actual': 'Domicilio ficticio de prueba',
    'carrera': 'LIC. EN ENFERMERIA', 'servicio_id': '1'}


def clear_records():
    # Solo la base _test. Resolver la referencia circular en la misma transacción.
    db.session.execute(db.update(Funcionario).values(foto_ruta=None))
    from employment_cleanup import clear_employment_test_rows
    clear_employment_test_rows()
    for model in (DocumentoAdjunto, DetalleCambioGuardia, CambioGuardia, Justificativo, Reposo, Vacacion, Comisionado,
                  Funcionario, HistorialAdministrativo):
        db.session.execute(db.delete(model))
    db.session.commit()


@pytest.fixture(autouse=True)
def isolated_employees(app, accounts, tmp_path):
    old = app.extensions['document_storage']
    app.extensions['document_storage'] = LocalStorage(tmp_path/'private-employees')
    with app.app_context(): clear_records()
    yield
    with app.app_context():
        db.session.rollback(); clear_records()
    app.extensions['document_storage'] = old


def create_person(client, photos=(), values=None):
    data = fields(client, BASE+'nuevo', values or DATA)
    result = upload(client, BASE+'nuevo', data, photos)
    assert result.status_code == 303, result.text
    rid = int(result.location.rsplit('/',1)[-1])
    return rid, data


def search_data(client, cedula):
    data = fields(client, BASE)
    return {**data, 'cedula': cedula}


def ticket(client, path):
    page = client.get(path)
    token = re.search(r'data-context="([^"]+)"',page.text).group(1)
    csrf = re.search(r'name="csrf_token"[^>]*value="([^"]*)"',page.text).group(1)
    return token, csrf


def lookup(client, token, csrf, cedula='1.234.567'):
    return client.post(BASE+'buscar-para-carga', json={'contexto':token,'cedula':cedula}, headers={'X-CSRFToken':csrf})


@pytest.mark.parametrize('role',['SUPERADMIN','JEFATURA'])
def test_create_search_full_profile_and_audit(app, accounts, role):
    client=client_for(app,accounts,role)
    assert 'Funcionario' in client.get('/').text
    rid,_=create_person(client)
    for value in ('1234567','1.234.567','001234567'):
        result=client.post(BASE,data=search_data(client,value))
        assert result.status_code==303 and result.location.endswith(f'/{rid}')
    with patch('app.employees.views.paraguay_today',return_value=date(2026,10,22)):
        profile=client.get(BASE+str(rid))
    assert profile.status_code==200
    for value in ('Ana María López Benítez','1234567','15/05/1990','36 años',
                  '11 años, 7 meses y 12 días','Domicilio ficticio de prueba','LIC. EN ENFERMERIA','Vínculos laborales','EDITAR FICHA'):
        assert value in profile.text
    assert 'Funcionario sin fotografía' in profile.text
    with app.app_context():
        record=db.session.get(Funcionario,rid)
        assert record.cedula=='1234567' and record.cantidad_vinculos==1
        assert record.usuario_registro_id==accounts[0][role][0]
        assert record.foto_ruta is None
        columns={c['name'] for c in db.inspect(db.engine).get_columns('funcionarios')}
        assert not {'edad','antiguedad','anio_ingreso'} & columns
    history=client.get(BASE+f'{rid}/historial')
    assert history.status_code==200 and 'FUNCIONARIO_CREADO' in history.text


def test_unknown_cedula_and_prefilled_creation(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN')
    response=client.post(BASE,data=search_data(client,'7.654.321'))
    assert response.status_code==200
    assert 'No se encontró ningún funcionario registrado con este número de cédula' in response.text
    assert '+ REGISTRAR NUEVO FUNCIONARIO' in response.text
    assert '7654321' not in response.headers.get('Location','')
    prepared=client.post(BASE+'nuevo',data={**search_data(client,'7.654.321'),'accion':'preparar'})
    assert prepared.status_code==200 and 'value="7654321"' in prepared.text
    with app.app_context(): assert db.session.scalar(db.select(db.func.count()).select_from(Funcionario))==0


@pytest.mark.parametrize('query,expected', [
    ('Ana María López Benítez', (0,)),
    ('María', (0, 1)),
    ('González', (1, 2)),
    ('María González', (1,)),
    ('gOnZáLeZ', (1, 2)),
    ('LóP', (0,)),
    ('Bení', (0,)),
    ('del Carm', (1,)),
    ('  María   del Carmen  González de la Cruz  ', (1,)),
    ('Desconocido', ()),
    ('María%', ()),
    ('_', ()),
])
def test_directory_search_names_compounds_and_literal_fragments(app, accounts, query, expected):
    client = client_for(app, accounts, 'SUPERADMIN')
    first, _ = create_person(client)
    second, _ = create_person(client, values={**DATA, 'cedula': '7654321',
        'nombres': 'María del Carmen', 'apellidos': 'González de la Cruz'})
    third, _ = create_person(client, values={**DATA, 'cedula': '7654322',
        'nombres': 'Luis', 'apellidos': 'González'})
    result = client.post(BASE, data=search_data(client, query))
    # Puntuación sin letras sigue la validación anterior de cédula.
    assert result.status_code == (422 if query == '_' else 200)
    found = {int(value) for value in re.findall(r'href="/funcionarios/(\d+)"', result.text)}
    ids = (first, second, third)
    assert found == {ids[index] for index in expected}
    if expected:
        assert 'Funcionarios encontrados' in result.text
        assert client.get(BASE + str(ids[expected[0]])).status_code == 200
    elif query != '_':
        assert 'No se encontraron funcionarios con ese nombre o apellido.' in result.text
        assert 'name="accion" value="preparar"' not in result.text
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Funcionario)) == 3


@pytest.mark.parametrize('value', ['0', '12..345', '1 234', '1234567890123', '１２３４', '١٢٣٤'])
def test_directory_keeps_invalid_numeric_cedula_validation(app, accounts, value):
    client = client_for(app, accounts, 'SUPERADMIN')
    assert client.post(BASE, data=search_data(client, value)).status_code == 422


def test_duplicate_normalized_cedula_and_idempotent_submission(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN')
    rid,data=create_person(client,[photo()])
    assert upload(client,BASE+'nuevo',data,[photo()]).status_code==303
    duplicate=upload(client,BASE+'nuevo',fields(client,BASE+'nuevo',{**DATA,'cedula':'001234567'}),[])
    assert duplicate.status_code==409 and 'Ya existe una ficha' in duplicate.text
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Funcionario))==1
        assert db.session.scalar(db.select(db.func.count()).select_from(DocumentoAdjunto))==1


@pytest.mark.parametrize('value',['','0','0.000.000','ABC123','123-456','12..345','12.34','1 234','1e7','1234567890123','１２３４','١٢٣٤'])
def test_invalid_cedulas_rejected(app,accounts,value):
    client=client_for(app,accounts,'SUPERADMIN')
    assert upload(client,BASE+'nuevo',fields(client,BASE+'nuevo',{**DATA,'cedula':value}),[]).status_code==422
    with app.app_context(): assert db.session.scalar(db.select(db.func.count()).select_from(Funcionario))==0


@pytest.mark.parametrize('changes',[{'nombres':' '},{'apellidos':''},{'direccion_actual':' '},
    {'fecha_nacimiento':'01/01/2999'},{'fecha_nacimiento':'31/02/1990'}, {'fecha_ingreso':'01/01/2999'},
    {'fecha_ingreso':'1985'},{'fecha_ingreso':'01/01/1980'},{'carrera':''},{'carrera':'INVENTADA'},
    {'servicio_id':'0'},{'servicio_id':'9999999'}])
def test_validates_required_dates_links_and_service(app,accounts,changes):
    client=client_for(app,accounts,'SUPERADMIN')
    response=upload(client,BASE+'nuevo',fields(client,BASE+'nuevo',{**DATA,**changes}),[])
    assert response.status_code==422,response.text
    with app.app_context(): assert db.session.scalar(db.select(db.func.count()).select_from(Funcionario))==0


def test_derived_count_and_authorized_edit_keep_creator_and_audit_without_pii(app,accounts):
    client=client_for(app,accounts,'JEFATURA'); rid,_=create_person(client,values={**DATA,'cantidad_vinculos':'0'})
    original=fields(client,BASE+f'{rid}/editar',{**DATA,'cantidad_vinculos':'0','direccion_actual':'Nueva dirección de prueba'})
    result=upload(client,BASE+f'{rid}/editar',original,[])
    assert result.status_code==303,result.text
    assert 'Nueva dirección de prueba' in client.get(BASE+str(rid)).text
    assert upload(client,BASE+f'{rid}/editar',original,[]).status_code==409
    with app.app_context():
        person=db.session.get(Funcionario,rid)
        assert person.cantidad_vinculos==1  # El contador enviado por el cliente se ignora.
        assert person.usuario_registro_id==person.usuario_modificacion_id==accounts[0]['JEFATURA'][0]
        events=db.session.scalars(db.select(HistorialAdministrativo).where(HistorialAdministrativo.entidad=='funcionarios')).all()
        stored=json.dumps([e.detalles for e in events])
        assert 'direccion_actual' in stored and 'Nueva' not in stored and '1234567' not in stored


def test_personal_photo_replacement_retention_and_restart(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN'); rid,_=create_person(client,[photo()])
    uri=BASE+f'{rid}/fotografia'
    assert client.get(uri).mimetype=='image/jpeg'
    with app.app_context():
        original=db.session.scalar(db.select(DocumentoAdjunto)); oldkey,oldid=original.ruta_almacenamiento,original.id
        assert original.tipo_modulo=='funcionarios' and original.funcionario_id==original.registro_id==rid
    url=uri+'/cambiar'
    response=upload(client,url,fields(client,url),[photo('JPEG','blue')])
    assert response.status_code==303,response.text
    with app.app_context():
        old=db.session.get(DocumentoAdjunto,oldid)
        assert not old.activo and old.usuario_retiro_id and old.motivo_retiro
        active=db.session.scalar(db.select(DocumentoAdjunto).where(DocumentoAdjunto.activo.is_(True)))
        assert db.session.get(Funcionario,rid).foto_ruta==active.ruta_vista
        assert db.session.scalar(db.select(db.func.count()).select_from(DocumentoAdjunto))==2
    assert app.extensions['document_storage'].path(oldkey).is_file()
    fresh=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':app.config['SQLALCHEMY_DATABASE_URI'],
        'SECRET_KEY':app.secret_key,'SESSION_COOKIE_SECURE':False,'DOCUMENT_LOCAL_ROOT':str(app.extensions['document_storage'].root)})
    visitor=fresh.test_client(); assert login(visitor).status_code==302
    assert visitor.get(uri).status_code==200
    assert 'FUNCIONARIO_FOTO_ACTUALIZADA' in client.get(BASE+f'{rid}/historial').text


@pytest.mark.parametrize('photos',[[(b'MZ invalid','fake.jpg')],[photo('PNG'),photo('JPEG','blue')],[(b'HEIC','test.heic')]])
def test_bad_photos_do_not_create_person(app,accounts,photos):
    client=client_for(app,accounts,'SUPERADMIN')
    assert upload(client,BASE+'nuevo',fields(client,BASE+'nuevo',DATA),photos).status_code==422
    with app.app_context(): assert db.session.scalar(db.select(db.func.count()).select_from(Funcionario))==0
    assert list(app.extensions['document_storage'].objects())==[]


def test_failed_photo_replacement_preserves_previous(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN'); rid,_=create_person(client,[photo()])
    url=BASE+f'{rid}/fotografia/cambiar'; data=fields(client,url)
    backend=app.extensions['document_storage']; before=dict(backend.objects())
    with patch.object(backend,'put',side_effect=OSError('simulated outage')):
        assert upload(client,url,data,[photo('PNG','red')]).status_code==503
    assert dict(backend.objects())==before
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(DocumentoAdjunto))==1
        assert db.session.scalar(db.select(DocumentoAdjunto)).activo
    assert client.get(BASE+f'{rid}/fotografia').status_code==200


@pytest.mark.parametrize('role',['OPERADOR','SUPERVISOR'])
def test_loading_roles_cannot_read_sensitive_profiles_but_have_scoped_lookup(app,accounts,role):
    admin=client_for(app,accounts,'SUPERADMIN'); rid,_=create_person(admin,[photo()])
    client=client_for(app,accounts,role)
    assert 'href="/funcionarios/"' not in client.get('/').text
    for path in (BASE, BASE+'nuevo', BASE+str(rid), BASE+f'{rid}/editar',BASE+f'{rid}/fotografia',BASE+f'{rid}/fotografia/cambiar',BASE+f'{rid}/historial'):
        assert client.get(path).status_code==403,path
    assert client.post(BASE+'nuevo',data=fields(client,'/justificativos/',DATA)).status_code==403
    token,csrf=ticket(client,'/justificativos/')
    result=lookup(client,token,csrf)
    assert result.status_code==200
    assert result.json=={'encontrado':True,'id':rid,'nombre_completo':'Ana María López Benítez'}
    assert 'Domicilio' not in result.text and '1990' not in result.text and 'foto' not in result.text
    assert result.headers['Cache-Control']=='no-store'
    assert client.get(BASE+'buscar-para-carga?cedula=1234567').status_code==405


def test_lookup_requires_auth_csrf_ticket_and_its_own_session(app,accounts):
    admin=client_for(app,accounts,'SUPERADMIN');create_person(admin)
    client=client_for(app,accounts,'OPERADOR'); token,csrf=ticket(client,'/justificativos/')
    assert client.post(BASE+'buscar-para-carga',json={'contexto':token,'cedula':'1234567'}).status_code==400
    assert lookup(client,'forged',csrf).status_code==403
    other=client_for(app,accounts,'SUPERVISOR'); _,othercsrf=ticket(other,'/reposo/')
    assert lookup(other,token,othercsrf).status_code==403
    unknown=lookup(client,token,csrf,'8888888')
    assert unknown.status_code==200 and not unknown.json['encontrado']
    assert lookup(client,token,csrf,'not-an-id').status_code==422
    with patch('app.employees.views.consume_lookup',return_value=False):
        assert lookup(client,token,csrf).status_code==429
    assert app.test_client().get(BASE).status_code==302


@pytest.mark.parametrize('path,data,model,key',PATHS)
def test_explicit_new_links_in_all_six_forms_keep_historical_names(app,accounts,path,data,model,key):
    admin=client_for(app,accounts,'SUPERADMIN'); rid,_=create_person(admin)
    second,_=create_person(admin,values={**DATA,'cedula':'7654321','nombres':'Luis','apellidos':'González'})
    operator=client_for(app,accounts,'OPERADOR')
    payload=fields(operator,path,data)
    if model is CambioGuardia:
        payload.update(solicitante='Ana María López Benítez',reemplazante='Luis González',
            solicitante_funcionario_id=str(rid),reemplazante_funcionario_id=str(second))
    else:
        payload.update(nombres_apellidos='Ana María López Benítez',funcionario_id=str(rid))
    response=operator.post(path,data=payload)
    assert response.status_code==303,response.text
    with app.app_context():
        row=db.session.scalar(db.select(model))
        assert (row.solicitante_funcionario_id if model is CambioGuardia else row.funcionario_id)==rid
        before=row.solicitante if model is CambioGuardia else row.nombres_apellidos
    updated=fields(admin,BASE+f'{rid}/editar',{**DATA,'nombres':'Ana Isabel'})
    assert upload(admin,BASE+f'{rid}/editar',updated,[]).status_code==303
    with app.app_context():
        row=db.session.scalar(db.select(model))
        assert (row.solicitante if model is CambioGuardia else row.nombres_apellidos)==before


def test_forged_employee_links_and_sql_photo_reassignment_rejected(app,accounts):
    admin=client_for(app,accounts,'SUPERADMIN'); rid,_=create_person(admin,[photo()]); second,_=create_person(admin,values={**DATA,'cedula':'7654321'})
    for value in (str(rid),'999999999','invalid'):
        payload=fields(admin,'/justificativos/',{'nombres_apellidos':'Persona diferente','fecha_inasistencia':'22/10/2026','motivo':'Motivo de prueba','funcionario_id':value})
        assert admin.post('/justificativos/',data=payload).status_code==422
    with app.app_context():
        photo_key=db.session.get(Funcionario,rid).foto_ruta
        for sql,params in [
            ('UPDATE funcionarios SET foto_ruta=:key WHERE id=:id',{'key':photo_key,'id':second}),
            ("UPDATE funcionarios SET cedula='1.234.567' WHERE id=:id",{'id':second}),
            ('UPDATE funcionarios SET cantidad_vinculos=-1 WHERE id=:id',{'id':second}),
            ('UPDATE funcionarios SET fecha_ingreso=DATE \'2999-01-01\' WHERE id=:id',{'id':second})]:
            with pytest.raises(SQLAlchemyError):
                db.session.execute(db.text(sql),params); db.session.commit()
            db.session.rollback()


def test_service_deactivation_does_not_prevent_other_authorized_edits(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN'); rid,_=create_person(client)
    with app.app_context():
        service=db.session.get(Servicio,1); service.activo=False; db.session.commit()
    try:
        data=fields(client,BASE+f'{rid}/editar',{**DATA,'direccion_actual':'Otra dirección de prueba'})
        assert upload(client,BASE+f'{rid}/editar',data,[]).status_code==303
    finally:
        with app.app_context():
            db.session.get(Servicio,1).activo=True; db.session.commit()


@pytest.mark.parametrize('birth,today,expected',[(date(1990,5,15),date(2026,10,22),36),
    (date(1990,12,1),date(2026,10,22),35),(date(2000,2,29),date(2025,2,28),25),
    (date(2000,2,29),date(2024,2,28),23)])
def test_completed_age_real_calendar(birth,today,expected): assert completed_age(birth,today)==expected


@pytest.mark.parametrize('entry,today,expected',[(date(2015,3,10),date(2026,10,22),(11,7,12)),
    (date(2024,1,31),date(2024,2,29),(0,1,0)),(date(2023,1,31),date(2023,3,1),(0,1,1)),
    (date(2024,2,29),date(2025,2,28),(1,0,0)),(date(2026,10,22),date(2026,10,22),(0,0,0))])
def test_tenure_real_months_and_leap_years(entry,today,expected): assert seniority(entry,today)==expected


def test_year_only_never_invents_exact_tenure(): assert seniority(None,date(2026,10,22)) is None
