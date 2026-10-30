from io import BytesIO
from uuid import uuid4, UUID
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import HiddenField, TextAreaField
from wtforms.validators import DataRequired, Length, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from app.extensions import db
from app.models import utcnow
from app.models.documents import DocumentoAdjunto
from app.hospital_services.records import CATEGORIES
from app.hospital_services.classification import audit
from app.security.permissions import permission_required, require
from app.documents.images import photos_field
from app.documents.service import attach, read_document
from app.documents.storage import DocumentError, StorageError

bp = Blueprint('documents', __name__, url_prefix='/documentos')


class UploadForm(FlaskForm):
    fotografias = photos_field()
    adjuntos_lote = HiddenField(default=lambda: str(uuid4()), validators=[DataRequired()])

    def validate_adjuntos_lote(self, field):
        try:
            UUID(field.data)
        except (ValueError, TypeError, AttributeError):
            raise ValidationError('Recarga la página para adjuntar fotografías.')


class RetireForm(FlaskForm):
    motivo = TextAreaField('Motivo del retiro', filters=[lambda s: (s or '').strip()],
        validators=[DataRequired(message='Indica el motivo del retiro.'), Length(min=3, max=1000)])


def parent(category_key, record_id, lock=False):
    category = CATEGORIES.get(category_key)
    if not category:
        abort(404)
    if category_key == 'reposos':
        require('diagnoses.read')
    query = db.select(category.model).where(category.model.id == record_id, category.model.eliminado.is_(False))
    if category.kind:
        query = query.where(category.model.tipo_cambio == category.kind)
    if lock:
        query = query.with_for_update(of=category.model).execution_options(populate_existing=True)
    record = db.session.scalar(query)
    if not record:
        abort(404)
    return category, record


def document_for(category_key, record_id, document_id):
    document = db.session.scalar(db.select(DocumentoAdjunto).where(DocumentoAdjunto.id == document_id,
        DocumentoAdjunto.tipo_modulo == category_key, DocumentoAdjunto.registro_id == record_id,
        DocumentoAdjunto.activo.is_(True)))
    if not document:
        abort(404)
    return document


@bp.route('/<category_key>/<int:record_id>/', methods=['GET', 'POST'])
@permission_required('documents.read')
def gallery(category_key, record_id):
    if request.method == 'POST':
        require('documents.manage')
    category, record = parent(category_key, record_id, lock=request.method == 'POST')
    form = UploadForm()
    status, error = 200, None
    if form.validate_on_submit():
        photos = form.fotografias.prepared
        try:
            if not photos:
                raise DocumentError('Selecciona al menos una fotografía.')
            attach(record, photos, form.adjuntos_lote.data, current_user.id)
            db.session.commit()
            flash('Documentos adjuntados correctamente', 'success')
            return redirect(url_for('documents.gallery', category_key=category_key, record_id=record.id), code=303)
        except DocumentError as exc:
            db.session.rollback()
            status, error = (503 if isinstance(exc, StorageError) else 422), str(exc)
        except SQLAlchemyError:
            db.session.rollback()
            status, error = 503, 'No se pudo guardar la carga. Vuelve a seleccionar las fotografías e inténtalo nuevamente.'
    elif request.method == 'POST':
        status = 422
    docs = db.session.scalars(db.select(DocumentoAdjunto).where(DocumentoAdjunto.tipo_modulo == category_key,
        DocumentoAdjunto.registro_id == record_id, DocumentoAdjunto.activo.is_(True)).order_by(DocumentoAdjunto.fecha_carga, DocumentoAdjunto.id)).all()
    history = []
    if request.args.get('historial') == '1':
        require('documents.history')
        history = db.session.scalars(db.select(DocumentoAdjunto).where(DocumentoAdjunto.tipo_modulo == category_key,
            DocumentoAdjunto.registro_id == record_id, DocumentoAdjunto.activo.is_(False)).order_by(DocumentoAdjunto.fecha_retiro.desc())).all()
    return render_template('documents/gallery.html', page_title='Documentos adjuntos', category=category,
        category_key=category_key, record=record, documents=docs, history=history, form=form, save_error=error), status


@bp.get('/<category_key>/<int:record_id>/<int:document_id>/vista')
@permission_required('documents.read')
def image(category_key, record_id, document_id):
    parent(category_key, record_id)
    document = document_for(category_key, record_id, document_id)
    data = read_document(document)
    # Solo una imagen regenerada, sin metadatos ni contenido adicional del original.
    return send_file(BytesIO(data), mimetype='image/jpeg', download_name=f'documento-{document.id}.jpg', max_age=0)


@bp.get('/<category_key>/<int:record_id>/<int:document_id>/descargar')
@permission_required('documents.download')
def download(category_key, record_id, document_id):
    _, record = parent(category_key, record_id)
    document = document_for(category_key, record_id, document_id)
    data = read_document(document, original=True)
    audit('DOCUMENTO_DESCARGADO', record.__tablename__, record.id, details={'documento_id': document.id})
    db.session.commit()
    extension = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}[document.tipo_mime]
    return send_file(BytesIO(data), mimetype=document.tipo_mime, as_attachment=True,
        download_name=f'documento-{document.id}.{extension}', max_age=0)


@bp.route('/<category_key>/<int:record_id>/<int:document_id>/retirar', methods=['GET', 'POST'])
@permission_required('documents.manage')
def retire(category_key, record_id, document_id):
    category, record = parent(category_key, record_id, lock=request.method == 'POST')
    document = document_for(category_key, record_id, document_id)
    form = RetireForm()
    if form.validate_on_submit():
        document.activo = False
        document.fecha_retiro, document.usuario_retiro_id, document.motivo_retiro = utcnow(), current_user.id, form.motivo.data
        audit('DOCUMENTO_RETIRADO', record.__tablename__, record.id,
              details={'documento_id': document.id, 'motivo': form.motivo.data})
        db.session.commit()
        flash('Documento retirado. El archivo y su historial se conservan.', 'success')
        return redirect(url_for('documents.gallery', category_key=category_key, record_id=record.id), code=303)
    return render_template('documents/retire.html', page_title='Retirar documento', category=category,
        category_key=category_key, record=record, document=document, form=form), 422 if request.method == 'POST' else 200
