from flask import current_app, render_template, request
from app.extensions import db


def configure_documents(app):
    from app.models.documents import DocumentoAdjunto
    from app.documents.storage import configure_storage, DocumentError, StorageError
    from app.documents.service import cleanup_pending, category_key
    from app.documents.views import bp
    from app.dashboard_clock import clock_snapshot
    configure_storage(app)
    app.register_blueprint(bp)
    from app.documents.maintenance import register_commands
    register_commands(app)
    base = app.request_class

    class DocumentRequest(base):
        @property
        def max_content_length(self):
            if self.method == 'POST' and self.mimetype == 'multipart/form-data' and self.blueprint == 'employees':
                return current_app.config['DOCUMENT_MAX_BYTES'] + 2 * 1024 * 1024
            if self.method == 'POST' and self.mimetype == 'multipart/form-data' and self.blueprint in {
                    'justificativos', 'reposo', 'guardias', 'vacaciones', 'comisionados', 'documents'}:
                return (current_app.config['DOCUMENT_MAX_BYTES'] * current_app.config['DOCUMENT_MAX_FILES'] + 2 * 1024 * 1024)
            return super().max_content_length

    app.request_class = DocumentRequest
    app.jinja_env.globals['document_category'] = category_key

    @app.context_processor
    def document_context():
        values = {'document_max_bytes': app.config['DOCUMENT_MAX_BYTES'], 'document_max_files': app.config['DOCUMENT_MAX_FILES']}
        if request.blueprint == 'documents':
            values['clock'] = clock_snapshot()
        return values

    @app.teardown_request
    def rollback_unfinished_uploads(error):
        if db.session.info.get('document_objects'):
            db.session.rollback()
            cleanup_pending(db.session)

    @app.errorhandler(DocumentError)
    def document_error(error):
        db.session.rollback()
        return render_template('error.html', title='Documento no disponible', message=str(error)), 503 if isinstance(error, StorageError) else 422

    @app.errorhandler(413)
    def upload_too_large(error):
        return render_template('error.html', title='Carga demasiado grande',
            message='La carga supera el límite permitido. Revisa la cantidad y el tamaño de las fotografías y vuelve a intentarlo.'), 413
