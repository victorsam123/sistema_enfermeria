"""Justificativos y cambios de guardia sin alterar tablas existentes."""
from alembic import op
import sqlalchemy as sa

revision = '0002_administrative_records'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def common_columns():
    return [
        sa.Column('usuario_registro_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('fecha_modificacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('solicitud_id', sa.Uuid(), nullable=False, unique=True),
    ]


def upgrade():
    op.create_table('justificativos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nombres_apellidos', sa.String(180), nullable=False),
        sa.Column('fecha_inasistencia', sa.Date(), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=False),
        sa.Column('fecha_cobertura', sa.Date(), nullable=False),
        sa.Column('usuario_modificacion_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='RESTRICT')),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        *common_columns(),
        sa.CheckConstraint('length(trim(nombres_apellidos)) BETWEEN 3 AND 180', name='justificativo_nombre_valido'),
        sa.CheckConstraint('length(trim(motivo)) BETWEEN 3 AND 4000', name='justificativo_motivo_valido'))
    op.create_index('ix_justificativos_fecha_inasistencia', 'justificativos', ['fecha_inasistencia'])
    op.create_index('ix_justificativos_fecha_cobertura', 'justificativos', ['fecha_cobertura'])
    op.create_table('cambios_guardia',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('solicitante', sa.String(180), nullable=False),
        sa.Column('reemplazante', sa.String(180), nullable=False),
        sa.Column('fecha_cambio', sa.Date(), nullable=False),
        sa.Column('hora_inicio', sa.Time(), nullable=False),
        sa.Column('hora_fin', sa.Time(), nullable=False),
        sa.Column('tipo_cambio', sa.String(10), nullable=False),
        *common_columns(),
        sa.CheckConstraint("tipo_cambio IN ('NORMAL', 'PAGADA')", name='cambio_tipo_valido'),
        sa.CheckConstraint('length(trim(solicitante)) BETWEEN 3 AND 180', name='cambio_solicitante_valido'),
        sa.CheckConstraint('length(trim(reemplazante)) BETWEEN 3 AND 180', name='cambio_reemplazante_valido'),
        sa.CheckConstraint(r"lower(regexp_replace(trim(solicitante), '\s+', ' ', 'g')) <> lower(regexp_replace(trim(reemplazante), '\s+', ' ', 'g'))", name='cambio_personas_distintas'),
        sa.CheckConstraint('hora_inicio <> hora_fin', name='cambio_horario_definido'))
    op.create_index('ix_cambios_guardia_tipo_fecha', 'cambios_guardia', ['tipo_cambio', 'fecha_cambio'])


def downgrade():
    raise RuntimeError('Reversión destructiva bloqueada: conservar justificativos y cambios. Crear una migración correctiva.')
