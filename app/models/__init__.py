from datetime import datetime, timezone
from sqlalchemy import event, inspect
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    rol = db.Column(db.String(40), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    protegido = db.Column(db.Boolean, nullable=False, default=False)
    debe_cambiar_password = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    fecha_modificacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now())
    sesion_version = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    version = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    fecha_creacion = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    ultimo_acceso = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        db.CheckConstraint("username <> 'victor' OR (protegido AND activo AND rol = 'SUPERADMIN')", name='victor_protegido'),
        db.CheckConstraint('NOT protegido OR activo', name='protegido_activo'),
        db.CheckConstraint("rol IN ('SUPERADMIN','JEFATURA','OPERADOR','SUPERVISOR')", name='usuario_rol_valido'),
        db.Index('uq_usuarios_username_normalizado', db.func.lower(username), unique=True),
    )
    __mapper_args__ = {'version_id_col': version}

    @property
    def rol_nombre(self):
        from app.security.permissions import ROLE_LABELS
        return ROLE_LABELS.get(self.rol, self.rol)

    @property
    def is_active(self):
        return self.activo

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='scrypt')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@event.listens_for(Usuario, 'before_delete')
def protect_delete(mapper, connection, target):
    if target.protegido or target.username == 'victor':
        raise ValueError('No se puede eliminar una cuenta protegida.')


@event.listens_for(Usuario, 'before_update')
def protect_update(mapper, connection, target):
    original = connection.execute(db.select(Usuario.__table__).where(Usuario.id == inspect(target).identity[0])).mappings().one()
    if original['protegido'] or original['username'] == 'victor':
        if (not target.activo or not target.protegido or target.username != original['username']
                or target.rol != original['rol'] or target.id != original['id']):
            raise ValueError('No se puede alterar la identidad, rol o estado de una cuenta protegida.')


class LogAcceso(db.Model):
    __tablename__ = 'logs_acceso'
    id = db.Column(db.BigInteger, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='SET NULL'))
    fecha_hora = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    tipo_evento = db.Column(db.String(40), nullable=False)
    direccion_ip = db.Column(db.String(45))


class IntentoLogin(db.Model):
    """Contador compartido entre procesos, persistente y actualizado bajo bloqueo."""
    __tablename__ = 'intentos_login'
    clave = db.Column(db.String(64), primary_key=True)
    inicio = db.Column(db.DateTime(timezone=True), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
