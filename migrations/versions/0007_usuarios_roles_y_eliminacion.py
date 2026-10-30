"""Roles canónicos, seguridad de sesiones, auditoría y eliminación lógica.

Revision ID: 0007_usuarios_roles_eliminacion
Revises: 0006_servicios_e_informes
"""
from alembic import op
import sqlalchemy as sa

revision = '0007_usuarios_roles_eliminacion'
down_revision = '0006_servicios_e_informes'
branch_labels = depends_on = None
TABLES = ('justificativos', 'reposos', 'cambios_guardia', 'vacaciones', 'comisionados')
ROLES = {'Superadministrador': 'SUPERADMIN', 'Jefatura de Enfermería': 'JEFATURA',
         'Operador': 'OPERADOR', 'Supervisor': 'SUPERVISOR'}


def upgrade():
    connection = op.get_bind()
    op.execute('LOCK TABLE usuarios IN ACCESS EXCLUSIVE MODE')
    existing = set(connection.execute(sa.text('SELECT DISTINCT rol FROM usuarios')).scalars())
    if existing - set(ROLES) - set(ROLES.values()):
        raise RuntimeError('Hay roles anteriores no reconocidos. Revisa su clasificación antes de migrar; no se asignan privilegios por suposición.')
    op.add_column('usuarios', sa.Column('debe_cambiar_password', sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column('usuarios', sa.Column('fecha_modificacion', sa.DateTime(timezone=True), nullable=True))
    op.add_column('usuarios', sa.Column('sesion_version', sa.Integer, nullable=False, server_default='1'))
    op.add_column('usuarios', sa.Column('version', sa.Integer, nullable=False, server_default='1'))
    # Bloqueo exclusivo y DDL transaccional: ninguna conexión externa puede
    # escribir durante la traducción del rol. Una falla restaura también el trigger.
    op.execute('DROP TRIGGER usuarios_proteger ON usuarios')
    op.drop_constraint('victor_protegido', 'usuarios', type_='check')
    for old, new in ROLES.items():
        connection.execute(sa.text('UPDATE usuarios SET rol=:new WHERE rol=:old'), {'old': old, 'new': new})
    op.execute('UPDATE usuarios SET fecha_modificacion=fecha_creacion WHERE fecha_modificacion IS NULL')
    op.alter_column('usuarios', 'fecha_modificacion', nullable=False, server_default=sa.func.now())
    op.alter_column('usuarios', 'debe_cambiar_password', server_default=sa.true())
    op.create_check_constraint('victor_protegido', 'usuarios', "username <> 'victor' OR (protegido AND activo AND rol='SUPERADMIN')")
    op.create_check_constraint('usuario_rol_valido', 'usuarios', "rol IN ('SUPERADMIN','JEFATURA','OPERADOR','SUPERVISOR')")
    op.create_index('uq_usuarios_username_normalizado', 'usuarios', [sa.text('lower(username)')], unique=True)
    op.execute('CREATE TRIGGER usuarios_proteger BEFORE UPDATE OR DELETE ON usuarios FOR EACH ROW EXECUTE FUNCTION proteger_usuario_permanente()')
    op.execute('''CREATE FUNCTION actualizar_seguridad_usuario() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF (NEW.password_hash,NEW.rol,NEW.activo,NEW.username,NEW.debe_cambiar_password)
           IS DISTINCT FROM (OLD.password_hash,OLD.rol,OLD.activo,OLD.username,OLD.debe_cambiar_password) THEN
            NEW.sesion_version := OLD.sesion_version + 1;
        ELSE NEW.sesion_version := OLD.sesion_version;
        END IF;
        IF (NEW.nombre,NEW.username,NEW.password_hash,NEW.rol,NEW.activo,NEW.protegido,NEW.debe_cambiar_password)
           IS DISTINCT FROM (OLD.nombre,OLD.username,OLD.password_hash,OLD.rol,OLD.activo,OLD.protegido,OLD.debe_cambiar_password) THEN
            NEW.fecha_modificacion := clock_timestamp();
        END IF;
        RETURN NEW;
    END $$''')
    op.execute('CREATE TRIGGER usuarios_actualizar_seguridad BEFORE UPDATE ON usuarios FOR EACH ROW EXECUTE FUNCTION actualizar_seguridad_usuario()')
    op.create_table('auditoria_usuarios', sa.Column('id', sa.BigInteger, primary_key=True),
        sa.Column('usuario_actor_id', sa.Integer, sa.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('usuario_afectado_id', sa.Integer, sa.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('accion', sa.String(50), nullable=False), sa.Column('fecha_hora', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('descripcion', sa.String(1000), nullable=False))
    for col in ('usuario_actor_id', 'usuario_afectado_id', 'fecha_hora'):
        op.create_index('ix_auditoria_usuarios_' + col, 'auditoria_usuarios', [col])
    op.execute('SET CONSTRAINTS ALL IMMEDIATE')
    for table in TABLES:
        op.add_column(table, sa.Column('eliminado', sa.Boolean, nullable=False, server_default=sa.false()))
        op.add_column(table, sa.Column('usuario_eliminacion_id', sa.Integer, nullable=True))
        op.add_column(table, sa.Column('fecha_eliminacion', sa.DateTime(timezone=True)))
        op.add_column(table, sa.Column('motivo_eliminacion', sa.String(1000)))
        op.create_foreign_key(f'fk_{table}_usuario_eliminacion', table, 'usuarios', ['usuario_eliminacion_id'], ['id'], ondelete='RESTRICT')
        op.create_index(f'ix_{table}_eliminado', table, ['eliminado'])
        op.create_check_constraint(f'{table}_eliminacion_completa', table,
            "(eliminado AND usuario_eliminacion_id IS NOT NULL AND fecha_eliminacion IS NOT NULL AND motivo_eliminacion IS NOT NULL AND length(trim(motivo_eliminacion)) BETWEEN 3 AND 1000) OR (NOT eliminado AND usuario_eliminacion_id IS NULL AND fecha_eliminacion IS NULL AND motivo_eliminacion IS NULL)")
    op.execute('SET CONSTRAINTS ALL DEFERRED')


def downgrade():
    raise RuntimeError('Reversión destructiva bloqueada: se conservan usuarios, auditorías y registros. Utiliza una migración correctiva revisada.')
