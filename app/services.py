import hashlib
import hmac
import os
from datetime import timedelta
import click
from flask import current_app, request
from sqlalchemy.dialects.postgresql import insert
from app.extensions import db
from app.models import Usuario, LogAcceso, IntentoLogin, utcnow


def initialize_admin():
    # Bloqueo transaccional: dos despliegues concurrentes no duplican la cuenta.
    db.session.execute(db.text('SELECT pg_advisory_xact_lock(71406251)'))
    existing = db.session.scalar(db.select(Usuario).where(Usuario.username == 'victor'))
    if existing:
        if not existing.protegido or not existing.activo or existing.rol != 'SUPERADMIN':
            raise RuntimeError('La cuenta victor existente necesita revisión; no se sobrescribió.')
        db.session.commit()
        return False
    password = os.getenv('INITIAL_ADMIN_PASSWORD')
    if not password:
        raise click.ClickException('Define INITIAL_ADMIN_PASSWORD en .env para la primera inicialización.')
    user = Usuario(nombre='Victor', username='victor', rol='SUPERADMIN', activo=True, protegido=True, debe_cambiar_password=False)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return True


def audit(event, user=None):
    db.session.add(LogAcceso(usuario_id=user.id if user else None, tipo_evento=event, direccion_ip=request.remote_addr))


def session_fingerprint(user):
    return hmac.new(current_app.secret_key.encode(), f'{user.id}:{user.password_hash}:{user.rol}:{int(user.activo)}:{user.sesion_version}'.encode(), hashlib.sha256).hexdigest()


def consume_login_attempt(username):
    now = utcnow()
    # Tanto la IP como la cuenta se limitan. Nunca se guarda el nombre introducido.
    for value in ('ip:' + (request.remote_addr or 'unknown'), 'user:' + username):
        key = hmac.new(current_app.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()
        db.session.execute(insert(IntentoLogin).values(clave=key, inicio=now, cantidad=0).on_conflict_do_nothing())
        row = db.session.scalar(db.select(IntentoLogin).where(IntentoLogin.clave == key).with_for_update())
        if now - row.inicio >= timedelta(minutes=15):
            row.inicio, row.cantidad = now, 0
        if row.cantidad >= 5:
            db.session.commit()
            return False
        row.cantidad += 1
    # Evita crecimiento indefinido de los contadores.
    db.session.execute(db.delete(IntentoLogin).where(IntentoLogin.inicio < now - timedelta(days=1)))
    db.session.commit()
    return True
