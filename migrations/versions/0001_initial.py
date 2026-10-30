"""Esquema inicial y barreras PostgreSQL para cuentas permanentes.

La reversión destructiva se rechaza explícitamente para conservar los datos.
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('usuarios',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nombre', sa.String(120), nullable=False),
        sa.Column('username', sa.String(80), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(256), nullable=False),
        sa.Column('rol', sa.String(40), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('protegido', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('ultimo_acceso', sa.DateTime(timezone=True)),
        sa.CheckConstraint("username <> 'victor' OR (protegido AND activo AND rol = 'Superadministrador')", name='victor_protegido'),
        sa.CheckConstraint('NOT protegido OR activo', name='protegido_activo'))
    op.create_table('logs_acceso',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='SET NULL')),
        sa.Column('fecha_hora', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('tipo_evento', sa.String(40), nullable=False),
        sa.Column('direccion_ip', sa.String(45)))
    op.create_index('ix_logs_acceso_fecha_hora', 'logs_acceso', ['fecha_hora'])
    op.create_table('intentos_login',
        sa.Column('clave', sa.String(64), primary_key=True),
        sa.Column('inicio', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cantidad', sa.Integer(), nullable=False))
    op.execute('''
        CREATE FUNCTION proteger_usuario_permanente() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.protegido OR OLD.username = 'victor' THEN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'No se puede eliminar una cuenta protegida';
                END IF;
                IF NEW.id IS DISTINCT FROM OLD.id
                    OR NEW.username IS DISTINCT FROM OLD.username
                    OR NEW.rol IS DISTINCT FROM OLD.rol
                    OR NEW.protegido IS DISTINCT FROM TRUE
                    OR NEW.activo IS DISTINCT FROM TRUE THEN
                    RAISE EXCEPTION 'No se puede alterar una cuenta protegida';
                END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER usuarios_proteger BEFORE UPDATE OR DELETE ON usuarios
        FOR EACH ROW EXECUTE FUNCTION proteger_usuario_permanente();
        CREATE FUNCTION impedir_truncado_usuarios() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'TRUNCATE de usuarios no permitido';
        END $$;
        CREATE TRIGGER usuarios_no_truncar BEFORE TRUNCATE ON usuarios
        FOR EACH STATEMENT EXECUTE FUNCTION impedir_truncado_usuarios();
    ''')


def downgrade():
    raise RuntimeError('Reversión destructiva bloqueada: conservar usuarios y registros. Crear una migración correctiva.')
