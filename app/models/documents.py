from sqlalchemy.dialects.postgresql import UUID
from app.extensions import db
from app.models import utcnow

OWNER_CHECK = """num_nonnulls(justificativo_id,reposo_id,cambio_guardia_id,vacacion_id,comisionado_id,funcionario_id)=1 AND (
 (tipo_modulo='justificativos' AND justificativo_id=registro_id) OR
 (tipo_modulo='reposos' AND reposo_id=registro_id) OR
 (tipo_modulo IN ('guardias','pagadas','reemplazos','emergencias') AND cambio_guardia_id=registro_id) OR
 (tipo_modulo='vacaciones' AND vacacion_id=registro_id) OR
 (tipo_modulo='comisionados' AND comisionado_id=registro_id) OR
 (tipo_modulo='funcionarios' AND funcionario_id=registro_id)) IS TRUE"""


class DocumentoAdjunto(db.Model):
    __tablename__ = 'documentos_adjuntos'
    id = db.Column(db.Integer, primary_key=True)
    tipo_modulo = db.Column(db.String(20), nullable=False)
    registro_id = db.Column(db.Integer, nullable=False)
    justificativo_id = db.Column(db.Integer, db.ForeignKey('justificativos.id', ondelete='RESTRICT'))
    reposo_id = db.Column(db.Integer, db.ForeignKey('reposos.id', ondelete='RESTRICT'))
    cambio_guardia_id = db.Column(db.Integer, db.ForeignKey('cambios_guardia.id', ondelete='RESTRICT'))
    vacacion_id = db.Column(db.Integer, db.ForeignKey('vacaciones.id', ondelete='RESTRICT'))
    comisionado_id = db.Column(db.Integer, db.ForeignKey('comisionados.id', ondelete='RESTRICT'))
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id', ondelete='RESTRICT'))
    nombre_original = db.Column(db.String(180), nullable=False)
    nombre_almacenamiento = db.Column(db.String(100), nullable=False, unique=True)
    tipo_mime = db.Column(db.String(40), nullable=False)
    tamano_bytes = db.Column(db.Integer, nullable=False)
    ruta_almacenamiento = db.Column(db.String(160), nullable=False, unique=True)
    ruta_vista = db.Column(db.String(160), nullable=False, unique=True)
    sha256 = db.Column(db.String(64), nullable=False)
    sha256_vista = db.Column(db.String(64), nullable=False)
    almacenamiento = db.Column(db.String(10), nullable=False)
    lote_id = db.Column(UUID(as_uuid=True), nullable=False)
    orden_lote = db.Column(db.Integer, nullable=False)
    usuario_carga_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    fecha_carga = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now())
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    fecha_retiro = db.Column(db.DateTime(timezone=True))
    usuario_retiro_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'))
    motivo_retiro = db.Column(db.String(1000))
    usuario_carga = db.relationship('Usuario', foreign_keys=[usuario_carga_id], lazy='joined')
    usuario_retiro = db.relationship('Usuario', foreign_keys=[usuario_retiro_id], lazy='joined')
    __table_args__ = (
        db.CheckConstraint(OWNER_CHECK, name='documento_propietario_unico'),
        db.CheckConstraint("tipo_mime IN ('image/jpeg','image/png','image/webp') AND tamano_bytes>0", name='documento_imagen_valida'),
        db.CheckConstraint("almacenamiento IN ('local','s3') AND orden_lote>=0", name='documento_almacenamiento_valido'),
        db.CheckConstraint("sha256 ~ '^[a-f0-9]{64}$' AND sha256_vista ~ '^[a-f0-9]{64}$'", name='documento_hash_valido'),
        db.CheckConstraint("(activo AND fecha_retiro IS NULL AND usuario_retiro_id IS NULL AND motivo_retiro IS NULL) OR (NOT activo AND fecha_retiro IS NOT NULL AND usuario_retiro_id IS NOT NULL AND motivo_retiro IS NOT NULL AND length(trim(motivo_retiro)) BETWEEN 3 AND 1000)", name='documento_retiro_auditado'),
        db.UniqueConstraint('tipo_modulo', 'registro_id', 'lote_id', 'orden_lote', name='documento_envio_unico'),
        db.Index('ix_documentos_registro_activo', 'tipo_modulo', 'registro_id', 'activo'),
        db.Index('uq_funcionario_foto_activa', 'funcionario_id', unique=True,
                 postgresql_where=db.text('funcionario_id IS NOT NULL AND activo')),
    )
