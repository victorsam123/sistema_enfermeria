"""Inicialización explícita, idempotente y sin create_all/drop_all."""
from flask_migrate import upgrade
from app import create_app
from app.services import initialize_admin
from app.extensions import db

app = create_app()
with app.app_context():
    revision = None
    if db.inspect(db.engine).has_table('alembic_version'):
        revision = db.session.execute(db.text('SELECT version_num FROM alembic_version')).scalar_one_or_none()
    db.session.remove()
    if revision == '0005_guardias_fechas_y_cobertura':
        # La primera ejecución de esta actualización exige un respaldo real.
        from scripts.migrar_actualizacion7 import main as migrate_with_backup
        migrate_with_backup()
        revision = '0006_servicios_e_informes'
    if revision == '0006_servicios_e_informes':
        from scripts.migrar_actualizacion8 import main as migrate_users_with_backup
        migrate_users_with_backup()
        revision = '0007_usuarios_roles_eliminacion'
    if revision == '0007_usuarios_roles_eliminacion':
        from scripts.migrar_actualizacion9 import main as migrate_documents_with_backup
        migrate_documents_with_backup()
        revision = '0008_documentos_adjuntos'
    if revision == '0008_documentos_adjuntos':
        from scripts.migrar_actualizacion10 import main as migrate_employees_with_backup
        migrate_employees_with_backup()
        revision = '0009_funcionarios'
    if revision == '0009_funcionarios':
        from scripts.migrar_actualizacion11 import main as migrate_employment_with_backup
        migrate_employment_with_backup()
    else:
        upgrade()
    created = initialize_admin()
    print('Base inicializada. Administrador creado.' if created else 'Base actualizada. Administrador conservado.')
