"""Respaldo conjunto privado: pg_dump, originales, vistas y manifiesto SHA-256.

Ejecutar con servidor detenido. No imprime contenido, nombres ni credenciales.
Guardar otra copia cifrada fuera de este equipo/bucket según la política local.
"""
import json
import os
import shutil
import subprocess
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from sqlalchemy.engine import make_url
from app import create_app
from app.extensions import db
from app.models.documents import DocumentoAdjunto
from app.documents.service import read_document


def main(backup_parent=None):
    app = create_app()
    with app.app_context():
        root = Path(app.root_path).parent.resolve()
        parent = Path(backup_parent) if backup_parent else root / '.runtime/backups'
        folder = parent / ('documentos_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        folder.mkdir(parents=True, mode=0o700)
        db.session.execute(db.text('SELECT pg_advisory_xact_lock(901,9)'))
        docs = db.session.scalars(db.select(DocumentoAdjunto).order_by(DocumentoAdjunto.id)).all()
        if any(doc.almacenamiento != app.config['DOCUMENT_STORAGE_BACKEND'] for doc in docs):
            raise RuntimeError('Hay documentos en otro almacenamiento. Conserva y respalda ambos antes de cambiar la configuración.')
        uri = make_url(app.config['SQLALCHEMY_DATABASE_URI'])
        executable = os.getenv('PG_DUMP') or shutil.which('pg_dump')
        if not executable:
            candidate = Path('C:/Program Files/PostgreSQL/18/bin/pg_dump.exe')
            executable = str(candidate) if candidate.is_file() else None
        if not executable:
            raise RuntimeError('Instala pg_dump o configura PG_DUMP. El respaldo no se completó.')
        env = os.environ.copy()
        env['PGPASSWORD'] = uri.password or ''
        if uri.query.get('sslmode'):
            env['PGSSLMODE'] = str(uri.query['sslmode'])
        dump = folder / 'postgres.dump'
        result = subprocess.run([executable, '--format=custom', '--file', str(dump), '--host', uri.host or 'localhost',
            '--port', str(uri.port or 5432), '--username', uri.username, '--dbname', uri.database, '--no-password'], env=env, capture_output=True)
        if result.returncode or not dump.is_file() or not dump.stat().st_size:
            raise RuntimeError('No se pudo completar pg_dump. El respaldo no es válido.')
        restore = str(Path(executable).with_name('pg_restore.exe' if os.name == 'nt' else 'pg_restore'))
        if subprocess.run([restore, '--list', str(dump)], capture_output=True).returncode:
            raise RuntimeError('No se pudo verificar el respaldo PostgreSQL.')
        manifest = {'version': 1, 'backend': app.config['DOCUMENT_STORAGE_BACKEND'],
            'postgres_sha256': sha256(dump.read_bytes()).hexdigest(), 'archivos': []}
        for doc in docs:
            for original, key in ((True, doc.ruta_almacenamiento), (False, doc.ruta_vista)):
                data = read_document(doc, original)
                target = folder / 'objetos' / key
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with target.open('xb') as stream:
                    os.chmod(target, 0o600)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                assert sha256(target.read_bytes()).hexdigest() == sha256(data).hexdigest()
                manifest['archivos'].append({'key': key, 'sha256': sha256(data).hexdigest(), 'bytes': len(data)})
        (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        db.session.commit()
        print('Respaldo conjunto verificado:', folder)
        print('Documentos incluidos (activos y retirados):', len(docs))


if __name__ == '__main__':
    main()
