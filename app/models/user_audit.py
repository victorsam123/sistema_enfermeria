from app.extensions import db
from app.models import utcnow


class AuditoriaUsuario(db.Model):
    __tablename__ = 'auditoria_usuarios'
    id = db.Column(db.BigInteger, primary_key=True)
    usuario_actor_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False, index=True)
    usuario_afectado_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False, index=True)
    accion = db.Column(db.String(50), nullable=False)
    fecha_hora = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, server_default=db.func.now(), index=True)
    descripcion = db.Column(db.String(1000), nullable=False)
    actor = db.relationship('Usuario', foreign_keys=[usuario_actor_id], lazy='joined')
    afectado = db.relationship('Usuario', foreign_keys=[usuario_afectado_id], lazy='joined')
