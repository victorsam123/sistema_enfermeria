"""Solo documentos emitidos; los justificativos originales no se alteran."""
from app.extensions import db
from app.models import utcnow
from sqlalchemy.dialects.postgresql import JSONB


class NotaCompensatoria(db.Model):
    __tablename__ = 'notas_compensatorias'
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.Integer, nullable=False)
    anio = db.Column(db.Integer, nullable=False)
    fecha_emision = db.Column(db.Date, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    solicitud_id = db.Column(db.Uuid, unique=True, nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    fecha_creacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now())
    registros = db.Column(JSONB, nullable=False)
    plantilla_sha256 = db.Column(db.String(64), nullable=False)
    documento_sha256 = db.Column(db.String(64), nullable=False)
    pdf_sha256 = db.Column(db.String(64), nullable=False)
    documento = db.deferred(db.Column(db.LargeBinary, nullable=False))
    pdf = db.deferred(db.Column(db.LargeBinary, nullable=False))
    __table_args__ = (
        db.UniqueConstraint('anio', 'numero', name='nota_numero_anual_unico'),
        db.CheckConstraint('numero > 0 AND anio=EXTRACT(YEAR FROM fecha_emision)', name='nota_identificacion_valida'),
        db.CheckConstraint("jsonb_typeof(registros)='array' AND jsonb_array_length(registros)>0", name='nota_registros_requeridos'),
    )
