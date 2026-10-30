"""Respaldo verificable y migración conservadora. Ejecutar con el servidor detenido.

No imprime credenciales ni filas de registros. Nunca reinicia tablas ni cuentas.
"""
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url
from flask_migrate import upgrade
from app import create_app
from app.extensions import db


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    app = create_app()
    with app.app_context():
        revision = db.session.execute(db.text('SELECT version_num FROM alembic_version')).scalar_one()
        if revision not in ('0006_servicios_e_informes', '0007_usuarios_roles_eliminacion'):
            raise RuntimeError('Aplica primero las actualizaciones anteriores con su respaldo. Esta migración requiere la actualización 7.')
        inspector = db.inspect(db.engine)
        quote = db.engine.dialect.identifier_preparer.quote
        snapshots = {}
        for table in ('usuarios', 'justificativos', 'reposos', 'cambios_guardia', 'detalles_cambio_guardia', 'vacaciones', 'comisionados', 'servicios', 'historial_administrativo'):
            columns = ','.join(quote(c['name']) for c in inspector.get_columns(table))
            query = db.text('SELECT ' + columns + ' FROM ' + quote(table) + ' ORDER BY id')
            snapshots[table] = query, db.session.execute(query).all()
        trigger_query = db.text("SELECT tgname,pg_get_triggerdef(oid) FROM pg_trigger WHERE tgrelid='usuarios'::regclass AND NOT tgisinternal ORDER BY tgname")
        triggers = db.session.execute(trigger_query).all()
        db.session.remove()
        uri = make_url(app.config['SQLALCHEMY_DATABASE_URI'])
        pg_dump = os.getenv('PG_DUMP') or shutil.which('pg_dump')
        if not pg_dump:
            candidate = Path('C:/Program Files/PostgreSQL/18/bin/pg_dump.exe')
            if candidate.is_file():
                pg_dump = str(candidate)
        if not pg_dump:
            raise RuntimeError('No se encontró pg_dump. Instala el cliente PostgreSQL o define PG_DUMP con su ruta. No se modificó la base.')
        backup_dir = root / '.runtime/backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / ('postgres_antes_actualizacion8_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.dump')
        env = os.environ.copy()
        env['PGPASSWORD'] = uri.password or ''
        if uri.query.get('sslmode'):
            env['PGSSLMODE'] = str(uri.query['sslmode'])
        command = [pg_dump, '--format=custom', '--file', str(backup), '--host', uri.host or 'localhost',
            '--port', str(uri.port or 5432), '--username', uri.username, '--dbname', uri.database, '--no-password']
        result = subprocess.run(command, env=env, capture_output=True)
        if result.returncode or not backup.is_file() or backup.stat().st_size == 0:
            raise RuntimeError('pg_dump no pudo crear el respaldo. Revisa conexión, permisos y versión del cliente. No se aplicó la migración.')
        restore = str(Path(pg_dump).with_name('pg_restore.exe' if os.name == 'nt' else 'pg_restore'))
        check = subprocess.run([restore, '--list', str(backup)], capture_output=True)
        if check.returncode:
            raise RuntimeError('No se pudo verificar el respaldo. No se aplicó la migración.')
        print('Respaldo PostgreSQL verificado:', backup)
        upgrade(revision='0007_usuarios_roles_eliminacion')
        role_mapping = {'Superadministrador':'SUPERADMIN', 'Jefatura de Enfermería':'JEFATURA', 'Operador':'OPERADOR', 'Supervisor':'SUPERVISOR'}
        for table, (query, original) in snapshots.items():
            expected = original
            if table == 'usuarios':
                expected = [tuple(role_mapping.get(value, value) if name == 'rol' else value for name, value in row._mapping.items()) for row in original]
            if [tuple(r) for r in db.session.execute(query).all()] != [tuple(r) for r in expected]:
                raise RuntimeError('La verificación posterior no coincide para ' + table + '. Mantén detenido el servidor y revisa el respaldo.')
        actual_triggers = db.session.execute(trigger_query).all()
        assert all(trigger in actual_triggers for trigger in triggers)
        assert db.session.execute(db.text('SELECT version_num FROM alembic_version')).scalar_one() == '0007_usuarios_roles_eliminacion'
        print('Migración verificada: todas las columnas anteriores, usuarios, hashes y protecciones conservados.')
        print('Roles traducidos a códigos estables. Contraseñas, estados, servicios, registros y protecciones conservados.')


if __name__ == '__main__':
    main()
