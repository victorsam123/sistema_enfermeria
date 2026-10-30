"""Catálogo persistente y trazabilidad de clasificación e informes."""
from sqlalchemy.orm import declared_attr
from sqlalchemy.dialects.postgresql import JSONB
from app.extensions import db
from app.models import utcnow

PENDING_CODE = 'PENDIENTE'


class Servicio(db.Model):
    __tablename__ = 'servicios'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    codigo = db.Column(db.String(40), nullable=False, unique=True)
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    fecha_creacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now())
    version = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        db.CheckConstraint('length(trim(nombre)) BETWEEN 2 AND 120', name='servicio_nombre_valido'),
        db.CheckConstraint("codigo ~ '^[A-Z0-9][A-Z0-9_-]{1,39}$'", name='servicio_codigo_valido'),
    )


class ServiceRecordMixin:
    @declared_attr
    def documentos_count(cls):
        from app.models.documents import DocumentoAdjunto
        field = {'justificativos': 'justificativo_id', 'reposos': 'reposo_id', 'cambios_guardia': 'cambio_guardia_id',
                 'vacaciones': 'vacacion_id', 'comisionados': 'comisionado_id'}[cls.__tablename__]
        return db.column_property(db.select(db.func.count(DocumentoAdjunto.id)).where(
            getattr(DocumentoAdjunto, field) == cls.id, DocumentoAdjunto.activo.is_(True)).correlate_except(DocumentoAdjunto).scalar_subquery())

    eliminado = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false(), index=True)
    fecha_eliminacion = db.Column(db.DateTime(timezone=True))
    motivo_eliminacion = db.Column(db.String(1000))

    @declared_attr
    def usuario_eliminacion_id(cls):
        return db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'))

    @declared_attr
    def servicio_id(cls):
        return db.Column(db.Integer, db.ForeignKey('servicios.id', ondelete='RESTRICT'), nullable=False, index=True)

    @declared_attr
    def servicio(cls):
        return db.relationship('Servicio', lazy='joined')


class HistorialAdministrativo(db.Model):
    __tablename__ = 'historial_administrativo'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    fecha_hora = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now(), index=True)
    evento = db.Column(db.String(40), nullable=False)
    entidad = db.Column(db.String(40), nullable=False)
    registro_id = db.Column(db.Integer)
    servicio_anterior_id = db.Column(db.Integer, db.ForeignKey('servicios.id', ondelete='RESTRICT'))
    servicio_nuevo_id = db.Column(db.Integer, db.ForeignKey('servicios.id', ondelete='RESTRICT'))
    detalles = db.Column(JSONB, nullable=False, default=dict, server_default='{}')
    usuario = db.relationship('Usuario', lazy='joined')
    servicio_anterior = db.relationship('Servicio', foreign_keys=[servicio_anterior_id], lazy='joined')
    servicio_nuevo = db.relationship('Servicio', foreign_keys=[servicio_nuevo_id], lazy='joined')
