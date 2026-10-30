"""Añade Comisionados y Vacaciones; no modifica tablas anteriores ni Reposo."""
from alembic import op
import sqlalchemy as sa

revision = '0003_comisionados_vacaciones'
down_revision = '0002_administrative_records'
branch_labels = None
depends_on = None


def audit_columns():
    return [
        sa.Column('usuario_registro_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('usuario_modificacion_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='RESTRICT')),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('fecha_modificacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('solicitud_id', sa.Uuid(), nullable=False, unique=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
    ]


def upgrade():
    op.create_table('comisionados',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nombres_apellidos', sa.String(180), nullable=False),
        sa.Column('fecha_inasistencia', sa.Date(), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=False),
        sa.Column('lugar', sa.String(250), nullable=False),
        *audit_columns(),
        sa.CheckConstraint('length(trim(nombres_apellidos)) BETWEEN 3 AND 180', name='comisionado_nombre_valido'),
        sa.CheckConstraint('length(trim(motivo)) BETWEEN 3 AND 2000', name='comisionado_motivo_valido'),
        sa.CheckConstraint('length(trim(lugar)) BETWEEN 2 AND 250', name='comisionado_lugar_valido'))
    op.create_index('ix_comisionados_fecha_inasistencia', 'comisionados', ['fecha_inasistencia'])
    op.create_table('vacaciones',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nombres_apellidos', sa.String(180), nullable=False),
        sa.Column('fecha_inicio', sa.Date(), nullable=False),
        sa.Column('fecha_termino', sa.Date(), nullable=False),
        sa.Column('total_dias', sa.Integer(), nullable=False),
        *audit_columns(),
        sa.CheckConstraint('length(trim(nombres_apellidos)) BETWEEN 3 AND 180', name='vacacion_nombre_valido'),
        sa.CheckConstraint('fecha_termino >= fecha_inicio', name='vacacion_fechas_validas'),
        sa.CheckConstraint('total_dias = (fecha_termino - fecha_inicio + 1)', name='vacacion_total_calendario'))
    op.create_index('ix_vacaciones_fecha_inicio', 'vacaciones', ['fecha_inicio'])
    op.create_index('ix_vacaciones_fecha_termino', 'vacaciones', ['fecha_termino'])


def downgrade():
    raise RuntimeError('Reversión destructiva bloqueada: conservar comisionados y vacaciones. Crear una migración correctiva.')
