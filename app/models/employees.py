from sqlalchemy.dialects.postgresql import UUID
from app.extensions import db
from app.models import utcnow


class Funcionario(db.Model):
    __tablename__ = 'funcionarios'
    id = db.Column(db.Integer, primary_key=True)
    nombres = db.Column(db.String(120), nullable=False)
    apellidos = db.Column(db.String(120), nullable=False)
    cedula = db.Column(db.String(12), nullable=False, unique=True)
    carrera = db.Column(db.String(80))
    fecha_nacimiento = db.Column(db.Date, nullable=False)
    fecha_ingreso = db.Column(db.Date, nullable=False)
    telefono = db.Column(db.String(15))
    cantidad_vinculos = db.Column(db.Integer, nullable=False, server_default='0')
    cantidad_vinculos_declarada = db.Column(db.Integer)
    direccion_actual = db.Column(db.String(500), nullable=False)
    servicio_id = db.Column(db.Integer, db.ForeignKey('servicios.id', ondelete='RESTRICT'), nullable=False, index=True)
    foto_ruta = db.Column(db.String(160), db.ForeignKey('documentos_adjuntos.ruta_vista',
        name='fk_funcionario_foto', ondelete='RESTRICT', deferrable=True, initially='DEFERRED', use_alter=True))
    usuario_registro_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    usuario_modificacion_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'))
    fecha_creacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now())
    fecha_modificacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now())
    solicitud_id = db.Column(UUID(as_uuid=True), nullable=False, unique=True)
    version = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    servicio = db.relationship('Servicio', lazy='joined')
    usuario_registro = db.relationship('Usuario', foreign_keys=[usuario_registro_id], lazy='joined')
    usuario_modificacion = db.relationship('Usuario', foreign_keys=[usuario_modificacion_id], lazy='joined')
    vinculos = db.relationship('VinculoLaboral', back_populates='funcionario', lazy='selectin',
        order_by='VinculoLaboral.numero_vinculo', cascade='save-update, merge', passive_deletes=True)
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        db.CheckConstraint("cedula ~ '^[1-9][0-9]{0,11}$'", name='funcionario_cedula_normalizada'),
        db.CheckConstraint("carrera IS NULL OR carrera IN ('LIC. EN ENFERMERIA','TEC. EN ENFERMERIA','AUX. EN ENFERMERA','CAMILLERO')", name='funcionario_carrera_valida'),
        db.CheckConstraint('cantidad_vinculos>=0', name='funcionario_vinculos_no_negativos'),
        db.CheckConstraint('cantidad_vinculos_declarada IS NULL OR cantidad_vinculos_declarada>=0', name='funcionario_declaracion_historica_valida'),
        db.CheckConstraint('fecha_ingreso>=fecha_nacimiento', name='funcionario_fechas_coherentes'),
        db.CheckConstraint("telefono IS NULL OR telefono ~ '^[0-9]{8,15}$'", name='funcionario_telefono_valido'),
        db.CheckConstraint("length(trim(nombres))>0 AND length(trim(apellidos))>0 AND length(nombres || ' ' || apellidos)<=180 AND length(trim(direccion_actual))>0", name='funcionario_datos_completos'),
    )

    @property
    def nombre_completo(self):
        return f'{self.nombres} {self.apellidos}'

    @property
    def eliminado(self):
        # Las fichas no tienen eliminación en esta etapa. Permite reutilizar
        # la transacción de almacenamiento privado de documentos.
        return False
