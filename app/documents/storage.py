"""Objetos privados. Nunca se publican rutas locales ni enlaces del proveedor."""
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from flask import current_app


class DocumentError(ValueError):
    pass


class StorageError(DocumentError):
    pass


KEY = re.compile(r'^documentos/[a-f0-9]{32}/(?:original|vista)\.(?:jpg|png|webp)$')


def checked_key(key):
    if not KEY.fullmatch(key):
        raise StorageError('Referencia de documento no válida.')
    return key


class LocalStorage:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def path(self, key):
        path = (self.root / checked_key(key)).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError('Referencia de documento no válida.')
        return path

    def put(self, key, data, mime):
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Identificadores aleatorios y creación exclusiva: nunca sobrescribir.
        with path.open('xb') as stream:
            os.chmod(path, 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

    def get(self, key, limit):
        with self.path(key).open('rb') as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise StorageError('El documento almacenado supera el límite permitido.')
        return data

    def delete(self, key):
        self.path(key).unlink(missing_ok=True)

    def objects(self):
        if not self.root.exists():
            return
        for path in self.root.glob('documentos/*/*'):
            if path.is_file():
                key = path.relative_to(self.root).as_posix()
                if KEY.fullmatch(key):
                    yield key, path.stat().st_mtime


class S3Storage:
    def __init__(self, config):
        import boto3
        from botocore.config import Config
        self.bucket = config['DOCUMENT_S3_BUCKET']
        self.sse = config['DOCUMENT_S3_SSE']
        self.client = boto3.client('s3', endpoint_url=config['DOCUMENT_S3_ENDPOINT'],
            region_name=config['DOCUMENT_S3_REGION'], aws_access_key_id=config['DOCUMENT_S3_ACCESS_KEY'],
            aws_secret_access_key=config['DOCUMENT_S3_SECRET_KEY'],
            config=Config(connect_timeout=5, read_timeout=30, retries={'max_attempts': 2, 'mode': 'standard'},
                          s3={'addressing_style': 'path'}))

    def put(self, key, data, mime):
        options = {'ServerSideEncryption': self.sse} if self.sse else {}
        self.client.put_object(Bucket=self.bucket, Key=checked_key(key), Body=data,
            ContentType=mime, CacheControl='private, no-store', **options)

    def get(self, key, limit):
        result = self.client.get_object(Bucket=self.bucket, Key=checked_key(key))
        stream = result['Body']
        try:
            data = stream.read(limit + 1)
        finally:
            stream.close()
        if len(data) > limit:
            raise StorageError('El documento almacenado supera el límite permitido.')
        return data

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=checked_key(key))

    def objects(self):
        for page in self.client.get_paginator('list_objects_v2').paginate(Bucket=self.bucket, Prefix='documentos/'):
            for item in page.get('Contents', []):
                if KEY.fullmatch(item['Key']):
                    yield item['Key'], item['LastModified'].timestamp()


def configure_storage(app):
    cfg = app.config
    if not (1 <= cfg['DOCUMENT_MAX_FILES'] <= 20 and 1 <= cfg['DOCUMENT_MAX_BYTES'] <= 32 * 1024 * 1024
            and 1 <= cfg['DOCUMENT_MAX_PIXELS'] <= 80000000 and 600 <= cfg['DOCUMENT_PREVIEW_EDGE'] <= 4000):
        raise RuntimeError('Límites de documentos fuera del rango permitido.')
    backend = cfg['DOCUMENT_STORAGE_BACKEND']
    if backend == 'local':
        root = Path(cfg['DOCUMENT_LOCAL_ROOT'] or Path(app.instance_path) / 'documentos_privados').resolve()
        forbidden = [Path(app.static_folder).resolve()]
        if not app.testing:
            forbidden.append(Path(tempfile.gettempdir()).resolve())
        if any(root == p or root.is_relative_to(p) for p in forbidden):
            raise RuntimeError('Los documentos requieren una ubicación privada y persistente fuera de static y temporales.')
        project = Path(app.root_path).parent.resolve()
        if not app.testing and root.is_relative_to(project) and not root.is_relative_to(Path(app.instance_path).resolve()):
            raise RuntimeError('Dentro del proyecto usa instance/documentos_privados, excluido del repositorio.')
        if cfg['PRODUCTION'] and (not cfg['DOCUMENT_LOCAL_ROOT'] or not cfg['DOCUMENT_LOCAL_PERSISTENT']):
            raise RuntimeError('En producción configura S3 o DOCUMENT_LOCAL_ROOT en un volumen persistente y DOCUMENT_LOCAL_PERSISTENT=true.')
        app.extensions['document_storage'] = LocalStorage(root)
    elif backend == 's3':
        endpoint = cfg['DOCUMENT_S3_ENDPOINT']
        if not cfg['DOCUMENT_S3_BUCKET'] or (endpoint and urlparse(endpoint).scheme != 'https'):
            raise RuntimeError('Configura un bucket privado y un endpoint S3 HTTPS válido.')
        app.extensions['document_storage'] = S3Storage(cfg)
    else:
        raise RuntimeError('DOCUMENT_STORAGE_BACKEND debe ser local o s3.')


def storage():
    return current_app.extensions['document_storage']
