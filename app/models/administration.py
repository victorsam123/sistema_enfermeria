"""Registros administrativos. No altera el modelo ni las protecciones de Usuario."""
from datetime import datetime, timedelta
from app.extensions import db
from app.models import utcnow
from app.models.hospital_services import ServiceRecordMixin


class Justificativo(ServiceRecordMixin, db.Model):
    __tablename__ = 'justificativos'
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id', ondelete='RESTRICT'))
    id = db.Column(db.Integer, primary_key=True)
    nombres_apellidos = db.Column(db.String(180), nullable=False)
    fecha_inasistencia = db.Column(db.Date, nullable=False, index=True)
    motivo = db.Column(db.Text, nullable=False)
    fecha_cobertura = db.Column(db.Date, nullable=True, index=True)
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
        db.CheckConstraint("(eliminado AND usuario_eliminacion_id IS NOT NULL AND fecha_eliminacion IS NOT NULL AND motivo_eliminacion IS NOT NULL AND length(trim(motivo_eliminacion)) BETWEEN 3 AND 1000) OR (NOT eliminado AND usuario_eliminacion_id IS NULL AND fecha_eliminacion IS NULL AND motivo_eliminacion IS NULL)", name='justificativos_eliminacion_completa'),
        db.CheckConstraint("length(trim(nombres_apellidos)) BETWEEN 3 AND 180", name='justificativo_nombre_valido'),
        db.CheckConstraint("length(trim(motivo)) BETWEEN 3 AND 4000", name='justificativo_motivo_valido'),
    )


class CambioGuardia(ServiceRecordMixin, db.Model):
    __tablename__ = 'cambios_guardia'
    solicitante_funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id', ondelete='RESTRICT'))
    reemplazante_funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id', ondelete='RESTRICT'))
    id = db.Column(db.Integer, primary_key=True)
    solicitante = db.Column(db.String(180), nullable=False)
    reemplazante = db.Column(db.String(180), nullable=False)
    fecha_cambio = db.Column(db.Date, nullable=False)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fin = db.Column(db.Time, nullable=False)
    tipo_cambio = db.Column(db.String(10), nullable=False)
    usuario_registro_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    fecha_creacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now())
    fecha_modificacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow, server_default=db.func.now())
    solicitud_id = db.Column(db.Uuid, nullable=False, unique=True)
    usuario_modificacion_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'))
    version = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    usuario_registro = db.relationship('Usuario', foreign_keys=[usuario_registro_id], lazy='joined')
    usuario_modificacion = db.relationship('Usuario', foreign_keys=[usuario_modificacion_id], lazy='joined')
    detalles = db.relationship('DetalleCambioGuardia', back_populates='cambio', lazy='selectin',
                              order_by='DetalleCambioGuardia.orden', cascade='save-update, merge')
    cupos = db.relationship('CambioGuardiaCupo', back_populates='cambio', lazy='noload',
                           order_by='CambioGuardiaCupo.participante', cascade='all, delete-orphan')
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        db.CheckConstraint("(eliminado AND usuario_eliminacion_id IS NOT NULL AND fecha_eliminacion IS NOT NULL AND motivo_eliminacion IS NOT NULL AND length(trim(motivo_eliminacion)) BETWEEN 3 AND 1000) OR (NOT eliminado AND usuario_eliminacion_id IS NULL AND fecha_eliminacion IS NULL AND motivo_eliminacion IS NULL)", name='cambios_guardia_eliminacion_completa'),
        db.CheckConstraint("tipo_cambio IN ('NORMAL', 'PAGADA', 'REEMPLAZO', 'EMERGENCIA')", name='cambio_tipo_valido'),
        db.CheckConstraint('solicitante_funcionario_id IS NULL OR reemplazante_funcionario_id IS NULL OR solicitante_funcionario_id<>reemplazante_funcionario_id', name='guardia_fichas_distintas'),
        db.CheckConstraint("length(trim(solicitante)) BETWEEN 3 AND 180", name='cambio_solicitante_valido'),
        db.CheckConstraint("length(trim(reemplazante)) BETWEEN 3 AND 180", name='cambio_reemplazante_valido'),
        db.CheckConstraint("lower(regexp_replace(trim(solicitante), '\\s+', ' ', 'g')) <> lower(regexp_replace(trim(reemplazante), '\\s+', ' ', 'g'))", name='cambio_personas_distintas'),
        db.CheckConstraint('hora_inicio <> hora_fin', name='cambio_horario_definido'),
        db.Index('ix_cambios_guardia_tipo_fecha', 'tipo_cambio', 'fecha_cambio'),
    )

    @property
    def finaliza_dia_siguiente(self):
        return self.hora_fin < self.hora_inicio

    @property
    def fecha_fin(self):
        return self.fecha_cambio + timedelta(days=int(self.finaliza_dia_siguiente))


class DetalleCambioGuardia(db.Model):
    __tablename__ = 'detalles_cambio_guardia'
    id = db.Column(db.Integer, primary_key=True)
    cambio_guardia_id = db.Column(db.Integer, db.ForeignKey('cambios_guardia.id', ondelete='RESTRICT'), nullable=False)
    participante = db.Column(db.String(1), nullable=False)
    funcionario = db.Column(db.String(180), nullable=False)
    fecha_guardia = db.Column(db.Date, nullable=False, index=True)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fin = db.Column(db.Time, nullable=False)
    codigo = db.Column(db.String(1))
    orden = db.Column(db.Integer, nullable=False)
    cambio = db.relationship('CambioGuardia', back_populates='detalles')
    __table_args__ = (
        db.CheckConstraint("participante IN ('S', 'R')", name='detalle_participante_valido'),
        db.CheckConstraint("codigo IS NULL OR codigo IN ('G', 'L', 'S', 'R')", name='detalle_codigo_valido'),
        db.CheckConstraint('hora_inicio <> hora_fin', name='detalle_horario_definido'),
        db.CheckConstraint('orden >= 0', name='detalle_orden_valido'),
        db.UniqueConstraint('cambio_guardia_id', 'orden', name='uq_detalle_guardia_orden'),
        db.UniqueConstraint('cambio_guardia_id', 'participante', 'fecha_guardia', 'hora_inicio', 'hora_fin', 'codigo',
            name='uq_detalle_guardia_evento', deferrable=True, initially='DEFERRED', postgresql_nulls_not_distinct=True),
    )

    @property
    def finaliza_dia_siguiente(self):
        return self.hora_fin < self.hora_inicio

    @property
    def fecha_fin(self):
        return self.fecha_guardia + timedelta(days=int(self.finaliza_dia_siguiente))


class CambioGuardiaCupo(db.Model):
    __tablename__ = 'cupos_cambios_guardia'
    id = db.Column(db.Integer, primary_key=True)
    cambio_guardia_id = db.Column(db.Integer, db.ForeignKey('cambios_guardia.id', ondelete='CASCADE'), nullable=False)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id', ondelete='RESTRICT'))
    funcionario_nombre = db.Column(db.String(180), nullable=False)
    participante = db.Column(db.String(1), nullable=False)
    tipo_cupo = db.Column(db.String(10), nullable=False)
    fecha_referencia = db.Column(db.Date, nullable=False)
    anio_imputacion = db.Column(db.Integer, nullable=False)
    mes_imputacion = db.Column(db.Integer, nullable=False)
    uso_anticipado = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    usuario_registro_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    fecha_creacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now())
    usuario_modificacion_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'))
    fecha_modificacion = db.Column(db.DateTime(timezone=True))
    version = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    cambio = db.relationship('CambioGuardia', back_populates='cupos')
    funcionario = db.relationship('Funcionario', lazy='joined')
    usuario_registro = db.relationship('Usuario', foreign_keys=[usuario_registro_id], lazy='joined')
    usuario_modificacion = db.relationship('Usuario', foreign_keys=[usuario_modificacion_id], lazy='joined')
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        db.CheckConstraint("participante IN ('S', 'R')", name='cupo_guardia_participante_valido'),
        db.CheckConstraint("tipo_cupo IN ('REEMPLAZO', 'PAGADA', 'EMERGENCIA')", name='cupo_guardia_tipo_valido'),
        db.CheckConstraint('mes_imputacion BETWEEN 1 AND 12 AND anio_imputacion BETWEEN 1900 AND 9999',
            name='cupo_guardia_periodo_valido'),
        db.CheckConstraint('length(trim(funcionario_nombre)) BETWEEN 3 AND 180', name='cupo_guardia_nombre_valido'),
        db.CheckConstraint("""NOT uso_anticipado OR (
            EXTRACT(DAY FROM fecha_referencia) >= 16 AND
            make_date(anio_imputacion, mes_imputacion, 1) =
                (date_trunc('month', fecha_referencia) + interval '1 month')::date)""",
            name='cupo_guardia_anticipo_siguiente_mes'),
        db.UniqueConstraint('cambio_guardia_id', 'participante', name='uq_cupo_guardia_cambio_participante'),
        db.Index('ix_cupo_guardia_funcionario_periodo',
            'funcionario_id', 'tipo_cupo', 'anio_imputacion', 'mes_imputacion'),
    )
