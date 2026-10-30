from sqlalchemy.dialects.postgresql import UUID
from app.extensions import db
from app.models import utcnow


class VinculoLaboral(db.Model):
    __tablename__ = 'vinculos_laborales'
    id = db.Column(db.Integer, primary_key=True)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id', ondelete='RESTRICT'), nullable=False, index=True)
    numero_vinculo = db.Column(db.Integer, nullable=False)
    fecha_ingreso = db.Column(db.Date, nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    usuario_registro_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    usuario_modificacion_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'))
    fecha_creacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now())
    fecha_modificacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now())
    motivo_estado = db.Column(db.String(1000))
    solicitud_id = db.Column(UUID(as_uuid=True), nullable=False, unique=True)
    version = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    funcionario = db.relationship('Funcionario', back_populates='vinculos')
    usuario_registro = db.relationship('Usuario', foreign_keys=[usuario_registro_id], lazy='joined')
    usuario_modificacion = db.relationship('Usuario', foreign_keys=[usuario_modificacion_id], lazy='joined')
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        db.UniqueConstraint('funcionario_id', 'numero_vinculo', name='uq_vinculo_numero_funcionario'),
        db.CheckConstraint('numero_vinculo>0', name='vinculo_numero_positivo'),
        db.CheckConstraint('activo OR (motivo_estado IS NOT NULL AND length(trim(motivo_estado)) BETWEEN 3 AND 1000)', name='vinculo_estado_justificado'),
    )


class DocumentoVinculoLaboral(db.Model):
    """Referencia futura a un archivo existente; no copia objetos físicos."""
    __tablename__ = 'documentos_vinculos_laborales'
    documento_id = db.Column(db.Integer, db.ForeignKey('documentos_adjuntos.id', ondelete='RESTRICT'), primary_key=True)
    vinculo_laboral_id = db.Column(db.Integer, db.ForeignKey('vinculos_laborales.id', ondelete='RESTRICT'), primary_key=True)
    usuario_asignacion_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    fecha_asignacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now())
