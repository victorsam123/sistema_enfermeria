"""Registro de reposos según foto 3. Solo añade una tabla nueva."""
from alembic import op
import sqlalchemy as sa

revision = '0004_reposos'
down_revision = '0003_comisionados_vacaciones'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('reposos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nombres_apellidos', sa.String(180), nullable=False),
        sa.Column('fecha_desde', sa.Date(), nullable=False),
        sa.Column('fecha_hasta', sa.Date(), nullable=False),
        sa.Column('total_dias', sa.Integer(), nullable=False),
        sa.Column('diagnostico', sa.Text(), nullable=False),
        sa.Column('fecha_entrega_departamento', sa.Date(), nullable=False),
        sa.Column('usuario_registro_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('usuario_modificacion_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='RESTRICT')),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('fecha_modificacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('solicitud_id', sa.Uuid(), nullable=False, unique=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.CheckConstraint('length(trim(nombres_apellidos)) BETWEEN 3 AND 180', name='reposo_nombre_valido'),
        sa.CheckConstraint('length(trim(diagnostico)) BETWEEN 1 AND 2000', name='reposo_diagnostico_valido'),
        sa.CheckConstraint('fecha_hasta >= fecha_desde', name='reposo_fechas_validas'),
        sa.CheckConstraint('total_dias = (fecha_hasta - fecha_desde + 1)', name='reposo_total_calendario'))
    for column in ('fecha_desde', 'fecha_hasta', 'fecha_creacion'):
        op.create_index('ix_reposos_' + column, 'reposos', [column])


def downgrade():
    raise RuntimeError('Reversión destructiva bloqueada: conservar los reposos y crear una migración correctiva.')
