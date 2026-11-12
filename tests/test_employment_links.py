from datetime import date
from uuid import uuid4
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import pytest
from flask_migrate import upgrade
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db
from app.models import Usuario
from app.models.employees import Funcionario
from app.models.employment_links import VinculoLaboral, DocumentoVinculoLaboral
from app.models.documents import DocumentoAdjunto
from app.models.hospital_services import HistorialAdministrativo
from app.employees.employment_services import add_link
from test_users_rbac import accounts, client_for, PATHS
from test_employees import clear_records, create_person, DATA
from test_documents import fields, upload, photo
from app.documents.storage import LocalStorage
from test_auth import login
from test_record_helpers import associate_employee


@pytest.fixture(autouse=True)
def isolated_links(app, accounts, tmp_path):
    old=app.extensions['document_storage'];app.extensions['document_storage']=LocalStorage(tmp_path/'private-links')
    with app.app_context(): clear_records()
    yield
    with app.app_context():
        db.session.rollback();clear_records()
    app.extensions['document_storage']=old


def link_fields(client,path,values=None):
    result=fields(client,path,values)
    page=client.get(path)
    import re
    for name in ('accion','confirmacion'):
        match=re.search(r'name="'+name+r'"[^>]*value="([^"]*)"',page.text)
        if match:result[name]=match.group(1)
    return result


def add(client,rid,entry='15/06/2020',payload=None):
    path=f'/funcionarios/{rid}/vinculos/nuevo'
    values=payload or link_fields(client,path,{'fecha_ingreso':entry})
    return client.post(path,data=values)


def link_ids(app,rid):
    with app.app_context():
        return db.session.scalars(db.select(VinculoLaboral.id).where(VinculoLaboral.funcionario_id==rid).order_by(VinculoLaboral.numero_vinculo)).all()


@pytest.mark.parametrize('role',['SUPERADMIN','JEFATURA'])
def test_three_links_one_person_one_photo_and_independent_tenures(app,accounts,role):
    client=client_for(app,accounts,role);rid,_=create_person(client,[photo()])
    with app.app_context():
        person=db.session.get(Funcionario,rid);signature=(person.cedula,person.foto_ruta,person.fecha_ingreso)
        photo_id=db.session.scalar(db.select(DocumentoAdjunto.id))
    assert add(client,rid,'15/06/2020').status_code==303
    assert add(client,rid,'01/02/2024').status_code==303
    with patch('app.employees.views.paraguay_today',return_value=date(2026,10,22)):
        profile=client.get(f'/funcionarios/{rid}')
    assert profile.status_code==200
    for text in ('VÍNCULO N.º 1','VÍNCULO N.º 2','VÍNCULO N.º 3','11 años, 7 meses y 12 días',
        '6 años, 4 meses y 7 días','2 años, 8 meses y 21 días','TOTAL DE VÍNCULOS ACTIVOS: <strong>3</strong>'):
        assert text in profile.text
    assert profile.text.count('class="employee-portrait"')==1
    with app.app_context():
        person=db.session.get(Funcionario,rid)
        assert person.cantidad_vinculos==3 and len(person.vinculos)==3
        assert (person.cedula,person.foto_ruta,person.fecha_ingreso)==signature
        assert db.session.scalar(db.select(db.func.count()).select_from(Funcionario))==1
        assert db.session.scalar(db.select(db.func.count()).select_from(DocumentoAdjunto))==1
        assert db.session.scalar(db.select(DocumentoAdjunto.id))==photo_id


def test_edit_only_second_date_preserves_identity_and_audits_old_new(app,accounts):
    client=client_for(app,accounts,'JEFATURA');rid,_=create_person(client)
    assert add(client,rid).status_code==303 and add(client,rid,'01/02/2024').status_code==303
    first,second,third=link_ids(app,rid)
    path=f'/funcionarios/{rid}/vinculos/{second}/editar'
    payload=link_fields(client,path,{'fecha_ingreso':'16/06/2020'})
    assert client.post(path,data=payload).status_code==303
    assert client.post(path,data=payload).status_code==409
    with app.app_context():
        assert db.session.get(VinculoLaboral,first).fecha_ingreso==date(2015,3,10)
        assert db.session.get(VinculoLaboral,second).fecha_ingreso==date(2020,6,16)
        assert db.session.get(VinculoLaboral,third).fecha_ingreso==date(2024,2,1)
        assert db.session.get(Funcionario,rid).fecha_ingreso==date(2015,3,10)
        event=db.session.scalar(db.select(HistorialAdministrativo).where(HistorialAdministrativo.evento=='VINCULO_MODIFICADO'))
        assert event.usuario_id==accounts[0]['JEFATURA'][0] and event.registro_id==rid
        assert event.detalles['vinculo_id']==second and event.detalles['numero_vinculo']==2
        assert event.detalles['fecha_ingreso_anterior']=='2020-06-15' and event.detalles['fecha_ingreso_nueva']=='2020-06-16'
    history=client.get(f'/funcionarios/{rid}/historial').text
    assert '15/06/2020' in history and '16/06/2020' in history


def test_deactivate_reactivate_no_delete_and_numbers_not_reused(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN');rid,_=create_person(client,[photo()])
    assert add(client,rid).status_code==303
    first,second=link_ids(app,rid)
    path=f'/funcionarios/{rid}/vinculos/{second}/estado'
    payload=link_fields(client,path,{'motivo':'Corrección administrativa','confirmacion':'CONFIRMAR'})
    assert client.post(path,data=payload).status_code==303
    assert client.post(path,data=payload).status_code==409
    with app.app_context():
        assert not db.session.get(VinculoLaboral,second).activo
        assert db.session.get(Funcionario,rid).cantidad_vinculos==1
        assert db.session.scalar(db.select(db.func.count()).select_from(VinculoLaboral))==2
    assert add(client,rid,'01/02/2024').status_code==303
    with app.app_context():assert [r.numero_vinculo for r in db.session.get(Funcionario,rid).vinculos]==[1,2,3]
    assert client.post(path,data=link_fields(client,path,{'motivo':'Reactivación autorizada','confirmacion':'CONFIRMAR'})).status_code==303
    with app.app_context():
        assert db.session.get(Funcionario,rid).cantidad_vinculos==3
        assert db.session.get(VinculoLaboral,second).activo
        for sql in ('DELETE FROM vinculos_laborales WHERE id=:id','TRUNCATE vinculos_laborales'):
            with pytest.raises(SQLAlchemyError):
                db.session.execute(db.text(sql),{'id':second});db.session.commit()
            db.session.rollback()
    assert client.get(f'/funcionarios/{rid}/fotografia').status_code==200


def test_all_links_can_be_inactive_total_zero_and_profile_stays(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN');rid,_=create_person(client)
    lid=link_ids(app,rid)[0];path=f'/funcionarios/{rid}/vinculos/{lid}/estado'
    assert client.post(path,data=link_fields(client,path,{'motivo':'Sin vínculo activo vigente','confirmacion':'CONFIRMAR'})).status_code==303
    with app.app_context():assert db.session.get(Funcionario,rid).cantidad_vinculos==0
    assert 'TOTAL DE VÍNCULOS ACTIVOS: <strong>0</strong>' in client.get(f'/funcionarios/{rid}').text


@pytest.mark.parametrize('entry',['','2020','06/2020','31/02/2020','01/01/2999','01/01/1980'])
def test_rejects_incomplete_future_and_before_birth(app,accounts,entry):
    client=client_for(app,accounts,'SUPERADMIN');rid,_=create_person(client)
    assert add(client,rid,entry).status_code==422
    with app.app_context():assert db.session.get(Funcionario,rid).cantidad_vinculos==1


def test_posted_count_number_and_tenure_are_not_authority(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN');rid,_=create_person(client,values={**DATA,'cantidad_vinculos':'999'})
    path=f'/funcionarios/{rid}/vinculos/nuevo'
    payload=link_fields(client,path,{'fecha_ingreso':'15/06/2020','numero_vinculo':'87','antiguedad':'900 años','anio_ingreso':'1999','cantidad_vinculos':'1000'})
    assert client.post(path,data=payload).status_code==303
    with app.app_context():
        person=db.session.get(Funcionario,rid)
        assert person.cantidad_vinculos==2 and person.vinculos[1].numero_vinculo==2
        with pytest.raises(SQLAlchemyError):
            db.session.execute(db.text('UPDATE funcionarios SET cantidad_vinculos=999 WHERE id=:id'),{'id':rid});db.session.commit()
        db.session.rollback()
        with pytest.raises(SQLAlchemyError):
            db.session.execute(db.text('UPDATE funcionarios SET fecha_ingreso=DATE \'2018-01-01\' WHERE id=:id'),{'id':rid});db.session.commit()
        db.session.rollback()
    edit=client.get(f'/funcionarios/{rid}/editar').text
    assert 'name="cantidad_vinculos"' not in edit and 'name="fecha_ingreso"' not in edit


def test_double_submission_same_date_and_more_than_three_links(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN');rid,_=create_person(client)
    payload=link_fields(client,f'/funcionarios/{rid}/vinculos/nuevo',{'fecha_ingreso':'10/03/2015'})
    assert add(client,rid,payload=payload).status_code==303
    assert add(client,rid,payload=payload).status_code==303
    assert add(client,rid,payload={**payload,'fecha_ingreso':'11/03/2015'}).status_code==422
    for year in (2018,2020,2024): assert add(client,rid,f'01/02/{year}').status_code==303
    with app.app_context():
        person=db.session.get(Funcionario,rid)
        assert person.cantidad_vinculos==5
        assert [v.numero_vinculo for v in person.vinculos]==[1,2,3,4,5]


def test_concurrent_assignments_serialized_without_duplicate_numbers(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN');rid,_=create_person(client)
    uid=accounts[0]['SUPERADMIN'][0]
    def submit(day):
        with app.app_context():
            row=add_link(rid,date(2020,6,day),uid,uuid4())
            number=row.numero_vinculo;db.session.commit();return number
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit,(15,16)))==[2,3]
    with app.app_context():assert db.session.get(Funcionario,rid).cantidad_vinculos==3


def test_preview_uses_server_paraguay_calendar_and_csrf(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN');rid,_=create_person(client)
    payload=link_fields(client,f'/funcionarios/{rid}/vinculos/nuevo')
    path=f'/funcionarios/{rid}/vinculos/calcular-antiguedad'
    assert client.post(path,json={'fecha_ingreso':'15/06/2020'}).status_code==400
    with patch('app.employees.employment_views.paraguay_today',return_value=date(2026,10,22)):
        response=client.post(path,json={'fecha_ingreso':'15/06/2020'},headers={'X-CSRFToken':payload['csrf_token']})
    assert response.status_code==200 and response.json=={'anio_ingreso':2020,'anios':6,'meses':4,'dias':7,'fecha_consulta':'22/10/2026'}
    assert response.headers['Cache-Control']=='no-store'
    assert client.post(path,json={'fecha_ingreso':'2020'},headers={'X-CSRFToken':payload['csrf_token']}).status_code==422


@pytest.mark.parametrize('role',['OPERADOR','SUPERVISOR'])
def test_loading_roles_denied_for_all_link_routes_and_expedient(app,accounts,role):
    admin=client_for(app,accounts,'SUPERADMIN');rid,_=create_person(admin)
    lid=link_ids(app,rid)[0];client=client_for(app,accounts,role)
    token=fields(client,'/justificativos/')['csrf_token']
    for suffix in ('nuevo',f'{lid}/editar',f'{lid}/estado','calcular-antiguedad'):
        path=f'/funcionarios/{rid}/vinculos/{suffix}'
        if suffix!='calcular-antiguedad':assert client.get(path).status_code==403
        assert client.post(path,data={'csrf_token':token,'fecha_ingreso':'01/01/2020'}).status_code==403
    assert client.get(f'/funcionarios/{rid}/expediente/justificativos').status_code==403
    with app.app_context():assert db.session.get(Funcionario,rid).cantidad_vinculos==1


def test_foreign_link_ids_and_missing_confirmations_rejected(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN');a,_=create_person(client);b,_=create_person(client,values={**DATA,'cedula':'7654321'})
    lid=link_ids(app,a)[0]
    for suffix in (f'{lid}/editar',f'{lid}/estado','0/editar'):
        assert client.get(f'/funcionarios/{b}/vinculos/{suffix}').status_code==404
    path=f'/funcionarios/{a}/vinculos/{lid}/estado'
    data=link_fields(client,path,{'motivo':'Prueba sin confirmación'})
    assert client.post(path,data=data).status_code==422
    assert client.post(path,data={**data,'confirmacion':'CONFIRMAR','motivo':' '}).status_code==422
    assert client.post(f'/funcionarios/{a}/vinculos/nuevo',data={'fecha_ingreso':'01/01/2020'}).status_code==400
    assert app.test_client().get(f'/funcionarios/{a}/vinculos/nuevo').status_code==302


def test_documents_can_reference_multiple_links_without_copying_and_not_another_person(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN');a,_=create_person(client,[photo()]);b,_=create_person(client,values={**DATA,'cedula':'7654321'})
    assert add(client,a).status_code==303
    ids=link_ids(app,a);other=link_ids(app,b)[0]
    files=dict(app.extensions['document_storage'].objects())
    with app.app_context():
        doc=db.session.scalar(db.select(DocumentoAdjunto))
        for lid in ids:
            db.session.add(DocumentoVinculoLaboral(documento_id=doc.id,vinculo_laboral_id=lid,usuario_asignacion_id=accounts[0]['SUPERADMIN'][0]))
        db.session.commit()
        assert db.session.scalar(db.select(db.func.count()).select_from(DocumentoAdjunto))==1
        with pytest.raises(SQLAlchemyError):
            db.session.add(DocumentoVinculoLaboral(documento_id=doc.id,vinculo_laboral_id=other,usuario_asignacion_id=accounts[0]['SUPERADMIN'][0]));db.session.commit()
        db.session.rollback()
    assert dict(app.extensions['document_storage'].objects())==files


@pytest.mark.parametrize('path,data,model,key',PATHS)
def test_expedient_reuses_only_explicitly_linked_records_and_documents(app,accounts,path,data,model,key):
    admin=client_for(app,accounts,'SUPERADMIN');rid,_=create_person(admin)
    payload=fields(admin,path,data)
    if hasattr(model,'solicitante'):
        payload.update(solicitante='Ana María López Benítez',solicitante_funcionario_id=str(rid))
    else:payload.update(nombres_apellidos='Ana María López Benítez',funcionario_id=str(rid))
    payload=associate_employee(app,payload,model,key,accounts[0]['SUPERADMIN'][0],rid)
    assert upload(admin,path,payload,[photo()]).status_code==303
    assert upload(admin,path,fields(admin,path,data),[]).status_code==303  # No se asocia por el nombre.
    response=admin.get(f'/funcionarios/{rid}/expediente/{key}')
    assert response.status_code==200 and '1 registros asociados' in response.text
    assert 'VER DOCUMENTOS ADJUNTOS' in response.text and '1 fotografía' in response.text
    profile=admin.get(f'/funcionarios/{rid}').text
    assert '1 registros' in profile and '1 fotografías adjuntas' in profile


def test_persistence_in_a_new_session_and_application(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN');rid,_=create_person(client,[photo()])
    assert add(client,rid).status_code==303 and add(client,rid,'01/02/2024').status_code==303
    fresh=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':app.config['SQLALCHEMY_DATABASE_URI'],
        'SECRET_KEY':app.secret_key,'SESSION_COOKIE_SECURE':False,'DOCUMENT_LOCAL_ROOT':str(app.extensions['document_storage'].root)})
    visitor=fresh.test_client();assert login(visitor).status_code==302
    assert 'TOTAL DE VÍNCULOS ACTIVOS: <strong>3</strong>' in visitor.get(f'/funcionarios/{rid}').text
    assert visitor.get(f'/funcionarios/{rid}/fotografia').status_code==200


def test_birth_edit_cannot_invalidate_an_earlier_link(app,accounts):
    client=client_for(app,accounts,'SUPERADMIN');rid,_=create_person(client)
    assert add(client,rid,'01/01/2000').status_code==303
    data=fields(client,f'/funcionarios/{rid}/editar',{**DATA,'fecha_nacimiento':'01/01/2005'})
    assert upload(client,f'/funcionarios/{rid}/editar',data,[]).status_code==422


def test_migration_preserves_historical_fields_and_does_not_invent_extra_links(app):
    schema='migracion11_'+uuid4().hex
    with app.app_context():
        assert make_url(app.config['SQLALCHEMY_DATABASE_URI']).database.endswith('_test')
        db.session.execute(db.text('CREATE SCHEMA '+schema));db.session.commit()
    isolated=create_app({'TESTING':True,'SECRET_KEY':app.secret_key,'SESSION_COOKIE_SECURE':False,
        'SQLALCHEMY_DATABASE_URI':app.config['SQLALCHEMY_DATABASE_URI'],
        'SQLALCHEMY_ENGINE_OPTIONS':{'connect_args':{'options':'-csearch_path='+schema}}})
    with isolated.app_context():
        upgrade(revision='0009_funcionarios')
        uid=db.session.execute(db.text("INSERT INTO usuarios(nombre,username,password_hash,rol,activo,protegido,debe_cambiar_password) VALUES('Victor','victor',:hash,'SUPERADMIN',true,true,false) RETURNING id"),{'hash':generate_password_hash('513625',method='scrypt')}).scalar_one()
        for index,quantity in enumerate((0,1,3)):
            db.session.execute(db.text("""INSERT INTO funcionarios(nombres,apellidos,cedula,fecha_nacimiento,fecha_ingreso,cantidad_vinculos,direccion_actual,servicio_id,usuario_registro_id,solicitud_id)
                VALUES('Nombre','Apellido',:ci,'1990-05-15','2015-03-10',:quantity,'Domicilio de prueba',1,:uid,:uuid)"""),{'ci':str(1000000+index),'quantity':quantity,'uid':uid,'uuid':uuid4()})
        db.session.commit()
        original=db.session.execute(db.text('SELECT * FROM funcionarios ORDER BY id')).all()
        user=db.session.execute(db.text('SELECT * FROM usuarios')).one()
        db.session.remove()  # Liberar lecturas antes del LOCK de la migración.
        upgrade()
        actual=db.session.execute(db.text('SELECT * FROM funcionarios ORDER BY id')).all()
        assert len(original)==len(actual)==3
        for old,new in zip(original,actual):
            assert all(old._mapping[k]==new._mapping[k] for k in old._mapping if k!='cantidad_vinculos')
            assert new._mapping['cantidad_vinculos_declarada']==old._mapping['cantidad_vinculos']
            assert new._mapping['cantidad_vinculos']==1
        rows=db.session.execute(db.text('SELECT funcionario_id,numero_vinculo,fecha_ingreso FROM vinculos_laborales ORDER BY funcionario_id')).all()
        assert len(rows)==3 and all(row.numero_vinculo==1 and row.fecha_ingreso==date(2015,3,10) for row in rows)
        assert db.session.execute(db.text('SELECT * FROM usuarios')).one()==user
        upgrade()  # Idempotente: no se agregan vínculos al reiniciar/migrar otra vez.
        assert db.session.execute(db.text('SELECT count(*) FROM vinculos_laborales')).scalar_one()==3
