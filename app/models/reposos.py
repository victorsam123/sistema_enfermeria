"""Registro de reposos según los campos confirmados de la foto 3."""
from app.extensions import db
from app.models import utcnow
from app.models.hospital_services import ServiceRecordMixin


class Reposo(ServiceRecordMixin, db.Model):
    __tablename__ = 'reposos'
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id', ondelete='RESTRICT'))
    id = db.Column(db.Integer, primary_key=True)
    nombres_apellidos = db.Column(db.String(180), nullable=False)
    fecha_desde = db.Column(db.Date, nullable=False, index=True)
    fecha_hasta = db.Column(db.Date, nullable=False, index=True)
    total_dias = db.Column(db.Integer, nullable=False)
    diagnostico = db.Column(db.Text, nullable=False)
    fecha_entrega_departamento = db.Column(db.Date, nullable=False)
    usuario_registro_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    usuario_modificacion_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'))
    fecha_creacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now(), index=True)
    fecha_modificacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow, server_default=db.func.now())
    solicitud_id = db.Column(db.Uuid, nullable=False, unique=True)
    version = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    usuario_registro = db.relationship('Usuario', foreign_keys=[usuario_registro_id], lazy='joined')
    usuario_modificacion = db.relationship('Usuario', foreign_keys=[usuario_modificacion_id], lazy='joined')
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        db.CheckConstraint("(eliminado AND usuario_eliminacion_id IS NOT NULL AND fecha_eliminacion IS NOT NULL AND motivo_eliminacion IS NOT NULL AND length(trim(motivo_eliminacion)) BETWEEN 3 AND 1000) OR (NOT eliminado AND usuario_eliminacion_id IS NULL AND fecha_eliminacion IS NULL AND motivo_eliminacion IS NULL)", name='reposos_eliminacion_completa'),
        db.CheckConstraint('length(trim(nombres_apellidos)) BETWEEN 3 AND 180', name='reposo_nombre_valido'),
        db.CheckConstraint('length(trim(diagnostico)) BETWEEN 1 AND 2000', name='reposo_diagnostico_valido'),
        db.CheckConstraint('fecha_hasta >= fecha_desde', name='reposo_fechas_validas'),
        db.CheckConstraint('total_dias = (fecha_hasta - fecha_desde + 1)', name='reposo_total_calendario'),
    )
