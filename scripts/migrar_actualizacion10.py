"""Respaldo conjunto antes de ampliar el esquema. Ejecutar con servidor detenido.

Lee columnas históricas mediante SQL de catálogo para poder respaldar antes
de que existan los nuevos modelos. Nunca imprime filas ni credenciales.
"""
import json
import os
import shutil
import subprocess
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from sqlalchemy.engine import make_url
from flask_migrate import upgrade
from app import create_app
from app.extensions import db
from app.documents.storage import storage


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    app = create_app()
    with app.app_context():
        revision = db.session.execute(db.text('SELECT version_num FROM alembic_version')).scalar_one()
        if revision not in ('0008_documentos_adjuntos', '0009_funcionarios'):
            raise RuntimeError('Aplica primero las actualizaciones anteriores con su respaldo. Se requiere la actualización 9.')
        inspector = db.inspect(db.engine)
        quote = db.engine.dialect.identifier_preparer.quote
        tables = ['usuarios', 'servicios', 'justificativos', 'reposos', 'cambios_guardia',
            'detalles_cambio_guardia', 'vacaciones', 'comisionados', 'documentos_adjuntos',
            'historial_administrativo', 'auditoria_usuarios', 'logs_acceso']
        if inspector.has_table('funcionarios'):
            tables.append('funcionarios')
        snapshots = {}
        for table in tables:
            columns = ','.join(quote(c['name']) for c in inspector.get_columns(table))
            query = db.text('SELECT ' + columns + ' FROM ' + quote(table) + ' ORDER BY id')
            snapshots[table] = query, db.session.execute(query).all()
        query = db.text("SELECT tgrelid::regclass::text,tgname,pg_get_triggerdef(oid) FROM pg_trigger WHERE tgrelid IN ('usuarios'::regclass,'documentos_adjuntos'::regclass,'cambios_guardia'::regclass) AND NOT tgisinternal ORDER BY tgrelid,tgname")
        triggers = db.session.execute(query).all()
        photos = db.session.execute(db.text('SELECT almacenamiento,ruta_almacenamiento,ruta_vista,sha256,sha256_vista FROM documentos_adjuntos ORDER BY id')).all()
        if any(row.almacenamiento != app.config['DOCUMENT_STORAGE_BACKEND'] for row in photos):
            raise RuntimeError('Hay documentos en otro backend. Respalda y configura ambos almacenamientos antes de migrar.')
        db.session.remove()
        uri = make_url(app.config['SQLALCHEMY_DATABASE_URI'])
        executable = os.getenv('PG_DUMP') or shutil.which('pg_dump')
        if not executable:
            candidate = Path('C:/Program Files/PostgreSQL/18/bin/pg_dump.exe')
            executable = str(candidate) if candidate.is_file() else None
        if not executable:
            raise RuntimeError('Instala pg_dump o configura PG_DUMP. No se modificó la base.')
        folder = root / '.runtime/backups' / ('antes_actualizacion10_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        folder.mkdir(parents=True, mode=0o700)
        dump = folder / 'postgres.dump'
        env = os.environ.copy()
        env['PGPASSWORD'] = uri.password or ''
        if uri.query.get('sslmode'):
            env['PGSSLMODE'] = str(uri.query['sslmode'])
        command = [executable, '--format=custom', '--file', str(dump), '--host', uri.host or 'localhost',
            '--port', str(uri.port or 5432), '--username', uri.username, '--dbname', uri.database, '--no-password']
        result = subprocess.run(command, env=env, capture_output=True)
        if result.returncode or not dump.is_file() or not dump.stat().st_size:
            raise RuntimeError('No se pudo completar el respaldo PostgreSQL. No se aplicó la migración.')
        restore = str(Path(executable).with_name('pg_restore.exe' if os.name == 'nt' else 'pg_restore'))
        if subprocess.run([restore, '--list', str(dump)], capture_output=True).returncode:
            raise RuntimeError('No se pudo verificar pg_dump. No se aplicó la migración.')
        manifest = {'version': 1, 'backend': app.config['DOCUMENT_STORAGE_BACKEND'],
            'postgres_sha256': sha256(dump.read_bytes()).hexdigest(), 'archivos': []}
        backend = storage()
        for photo in photos:
            for key, digest in ((photo.ruta_almacenamiento, photo.sha256), (photo.ruta_vista, photo.sha256_vista)):
                raw = backend.get(key, max(32 * 1024 * 1024, app.config['DOCUMENT_MAX_BYTES']))
                if sha256(raw).hexdigest() != digest:
                    raise RuntimeError('La integridad de un objeto no coincide. No se aplicó la migración.')
                target = folder / 'objetos' / key
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with target.open('xb') as stream:
                    os.chmod(target, 0o600)
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                if sha256(target.read_bytes()).hexdigest() != digest:
                    raise RuntimeError('No se verificó la copia documental. No se aplicó la migración.')
                manifest['archivos'].append({'key': key, 'sha256': digest, 'bytes': len(raw)})
        (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print('Respaldo PostgreSQL y documental verificado:', folder)
        upgrade(revision='0009_funcionarios')
        for table, (statement, original) in snapshots.items():
            if db.session.execute(statement).all() != original:
                raise RuntimeError('La verificación posterior no coincide para ' + table + '. Mantén detenido el servidor y revisa el respaldo.')
        after = db.session.execute(query).all()
        if not all(trigger in after for trigger in triggers):
            raise RuntimeError('La verificación de protecciones anteriores no coincide.')
        if db.session.execute(db.text('SELECT version_num FROM alembic_version')).scalar_one() != '0009_funcionarios':
            raise RuntimeError('La revisión final no coincide.')
        print('Migración verificada: columnas históricas, cuentas, hashes, servicios, documentos y auditorías conservados.')
        print('No se asociaron fichas por nombres ni se importaron datos personales.')


if __name__ == '__main__':
    main()
