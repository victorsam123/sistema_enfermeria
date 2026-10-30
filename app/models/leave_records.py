"""Tablas nuevas de Comisionados y Vacaciones, independientes de las anteriores."""
from app.extensions import db
from app.models import utcnow
from app.models.hospital_services import ServiceRecordMixin


class Comisionado(ServiceRecordMixin, db.Model):
    __tablename__ = 'comisionados'
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id', ondelete='RESTRICT'))
    id = db.Column(db.Integer, primary_key=True)
    nombres_apellidos = db.Column(db.String(180), nullable=False)
    fecha_inasistencia = db.Column(db.Date, nullable=False, index=True)
    motivo = db.Column(db.Text, nullable=False)
    lugar = db.Column(db.String(250), nullable=False)
    usuario_registro_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    usuario_modificacion_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'))
    fecha_creacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now())
    fecha_modificacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow, server_default=db.func.now())
    solicitud_id = db.Column(db.Uuid, nullable=False, unique=True)
    version = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    usuario_registro = db.relationship('Usuario', foreign_keys=[usuario_registro_id], lazy='joined')
    usuario_modificacion = db.relationship('Usuario', foreign_keys=[usuario_modificacion_id], lazy='joined')
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        db.CheckConstraint("(eliminado AND usuario_eliminacion_id IS NOT NULL AND fecha_eliminacion IS NOT NULL AND motivo_eliminacion IS NOT NULL AND length(trim(motivo_eliminacion)) BETWEEN 3 AND 1000) OR (NOT eliminado AND usuario_eliminacion_id IS NULL AND fecha_eliminacion IS NULL AND motivo_eliminacion IS NULL)", name='comisionados_eliminacion_completa'),
        db.CheckConstraint('length(trim(nombres_apellidos)) BETWEEN 3 AND 180', name='comisionado_nombre_valido'),
        db.CheckConstraint('length(trim(motivo)) BETWEEN 3 AND 2000', name='comisionado_motivo_valido'),
        db.CheckConstraint('length(trim(lugar)) BETWEEN 2 AND 250', name='comisionado_lugar_valido'),
    )


class Vacacion(ServiceRecordMixin, db.Model):
    __tablename__ = 'vacaciones'
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id', ondelete='RESTRICT'))
    id = db.Column(db.Integer, primary_key=True)
    nombres_apellidos = db.Column(db.String(180), nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False, index=True)
    fecha_termino = db.Column(db.Date, nullable=False, index=True)
    total_dias = db.Column(db.Integer, nullable=False)
    usuario_registro_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    usuario_modificacion_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'))
    fecha_creacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now())
    fecha_modificacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow, server_default=db.func.now())
    solicitud_id = db.Column(db.Uuid, nullable=False, unique=True)
    version = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    funcionario = db.relationship('Funcionario', foreign_keys=[funcionario_id], lazy='joined')
    usuario_registro = db.relationship('Usuario', foreign_keys=[usuario_registro_id], lazy='joined')
    usuario_modificacion = db.relationship('Usuario', foreign_keys=[usuario_modificacion_id], lazy='joined')
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        db.CheckConstraint("(eliminado AND usuario_eliminacion_id IS NOT NULL AND fecha_eliminacion IS NOT NULL AND motivo_eliminacion IS NOT NULL AND length(trim(motivo_eliminacion)) BETWEEN 3 AND 1000) OR (NOT eliminado AND usuario_eliminacion_id IS NULL AND fecha_eliminacion IS NULL AND motivo_eliminacion IS NULL)", name='vacaciones_eliminacion_completa'),
        db.CheckConstraint('length(trim(nombres_apellidos)) BETWEEN 3 AND 180', name='vacacion_nombre_valido'),
        db.CheckConstraint('fecha_termino >= fecha_inicio', name='vacacion_fechas_validas'),
        db.CheckConstraint('total_dias = (fecha_termino - fecha_inicio + 1)', name='vacacion_total_calendario'),
    )
