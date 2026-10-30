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
        if revision not in ('0005_guardias_fechas_y_cobertura', '0006_servicios_e_informes'):
            raise RuntimeError('Aplica primero las actualizaciones anteriores con su respaldo. Esta migración requiere la actualización 6.')
        inspector = db.inspect(db.engine)
        quote = db.engine.dialect.identifier_preparer.quote
        snapshots = {}
        for table in ('usuarios', 'justificativos', 'reposos', 'cambios_guardia', 'detalles_cambio_guardia', 'vacaciones', 'comisionados'):
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
        backup = backup_dir / ('postgres_antes_actualizacion7_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.dump')
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
        upgrade(revision='0006_servicios_e_informes')
        for table, (query, original) in snapshots.items():
            if db.session.execute(query).all() != original:
                raise RuntimeError('La verificación posterior no coincide para ' + table + '. Mantén detenido el servidor y revisa el respaldo.')
        assert db.session.execute(trigger_query).all() == triggers
        assert db.session.execute(db.text('SELECT version_num FROM alembic_version')).scalar_one() == '0006_servicios_e_informes'
        if revision == '0005_guardias_fechas_y_cobertura':
            for table in ('justificativos', 'reposos', 'cambios_guardia', 'vacaciones', 'comisionados'):
                assert db.session.execute(db.text(f"SELECT count(*) FROM {table} t JOIN servicios s ON s.id=t.servicio_id WHERE s.codigo<>'PENDIENTE'")).scalar_one() == 0
        print('Migración verificada: todas las columnas anteriores, usuarios, hashes y protecciones conservados.')
        print('Registros anteriores clasificados como PENDIENTE DE CLASIFICACIÓN, sin asignarles una procedencia inventada.')


if __name__ == '__main__':
    main()
