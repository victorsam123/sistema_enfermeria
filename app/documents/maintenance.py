"""Conciliación explícita: protege referencias activas y retiradas."""
import time
import click
from flask import current_app
from app.extensions import db
from app.models.documents import DocumentoAdjunto
from app.documents.storage import storage
from app.documents.service import read_document


def referenced_keys(connection=None):
    execute = connection.execute if connection is not None else db.session.execute
    rows = execute(db.select(DocumentoAdjunto.ruta_almacenamiento, DocumentoAdjunto.ruta_vista).where(
        DocumentoAdjunto.almacenamiento == current_app.config['DOCUMENT_STORAGE_BACKEND'])).all()
    return {key for row in rows for key in row}


def reconcile(clean=False, verify=False):
    # Coordinado con attach(): ningún PUT está en curso mientras se concilia.
    db.session.execute(db.text('SELECT pg_advisory_xact_lock(901,9)'))
    backend = storage()
    refs = referenced_keys()
    objects = dict(backend.objects())
    orphans = set(objects) - refs
    missing = refs - set(objects)
    retired = 0
    for key in orphans:
        if clean and time.time() - objects[key] >= 86400:
            # Reconsultar antes de borrar y conservar un margen de 24 horas.
            if key not in referenced_keys():
                backend.delete(key)
                retired += 1
    bad = 0
    if verify:
        for doc in db.session.scalars(db.select(DocumentoAdjunto).where(
                DocumentoAdjunto.almacenamiento == current_app.config['DOCUMENT_STORAGE_BACKEND'])):
            try:
                read_document(doc, original=True)
                read_document(doc)
            except Exception:
                bad += 1
    db.session.commit()
    return {'referencias': len(refs), 'objetos': len(objects), 'sin_referencia': len(orphans),
            'faltantes': len(missing), 'huerfanos_retirados': retired, 'integridad_fallida': bad}


def register_commands(app):
    @app.cli.command('conciliar-documentos')
    @click.option('--limpiar-huerfanos', is_flag=True, help='Retira solo objetos sin ninguna referencia y con más de 24 horas.')
    @click.option('--verificar', is_flag=True, help='Verifica SHA-256 de originales y vistas, también de documentos retirados.')
    def reconcile_command(limpiar_huerfanos, verificar):
        """Sin opciones solo informa. Nunca elimina documentos registrados."""
        try:
            result = reconcile(limpiar_huerfanos, verificar)
        except Exception as exc:
            db.session.rollback()
            raise click.ClickException('No se pudo conciliar. Revisa disponibilidad y permisos del almacenamiento.') from exc
        for key, value in result.items():
            click.echo(f'{key}: {value}')
        if result['faltantes'] or result['integridad_fallida']:
            raise click.ClickException('Revisa el respaldo antes de continuar: hay objetos faltantes o alterados.')
