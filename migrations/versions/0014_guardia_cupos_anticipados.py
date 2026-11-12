"""Persist monthly quota allocations independently from real guard dates.

Revision ID: 0014_guardia_cupos_anticipados
Revises: 0013_notas_compensatorias
"""
from alembic import op
import sqlalchemy as sa


revision = '0014_guardia_cupos_anticipados'
down_revision = '0013_notas_compensatorias'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cupos_cambios_guardia',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cambio_guardia_id', sa.Integer(),
            sa.ForeignKey('cambios_guardia.id', ondelete='CASCADE'), nullable=False),
        sa.Column('funcionario_id', sa.Integer(),
            sa.ForeignKey('funcionarios.id', ondelete='RESTRICT')),
        sa.Column('funcionario_nombre', sa.String(180), nullable=False),
        sa.Column('participante', sa.String(1), nullable=False),
        sa.Column('tipo_cupo', sa.String(10), nullable=False),
        sa.Column('fecha_referencia', sa.Date(), nullable=False),
        sa.Column('anio_imputacion', sa.Integer(), nullable=False),
        sa.Column('mes_imputacion', sa.Integer(), nullable=False),
        sa.Column('uso_anticipado', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('usuario_registro_id', sa.Integer(),
            sa.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('usuario_modificacion_id', sa.Integer(),
            sa.ForeignKey('usuarios.id', ondelete='RESTRICT')),
        sa.Column('fecha_modificacion', sa.DateTime(timezone=True)),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.CheckConstraint("participante IN ('S', 'R')", name='cupo_guardia_participante_valido'),
        sa.CheckConstraint("tipo_cupo IN ('REEMPLAZO', 'PAGADA', 'EMERGENCIA')", name='cupo_guardia_tipo_valido'),
        sa.CheckConstraint('mes_imputacion BETWEEN 1 AND 12 AND anio_imputacion BETWEEN 1900 AND 9999',
            name='cupo_guardia_periodo_valido'),
        sa.CheckConstraint('length(trim(funcionario_nombre)) BETWEEN 3 AND 180',
            name='cupo_guardia_nombre_valido'),
        sa.CheckConstraint("""NOT uso_anticipado OR (
            EXTRACT(DAY FROM fecha_referencia) >= 16 AND
            make_date(anio_imputacion, mes_imputacion, 1) =
                (date_trunc('month', fecha_referencia) + interval '1 month')::date)""",
            name='cupo_guardia_anticipo_siguiente_mes'),
        sa.UniqueConstraint('cambio_guardia_id', 'participante',
            name='uq_cupo_guardia_cambio_participante'),
    )
    op.create_index('ix_cupo_guardia_funcionario_periodo', 'cupos_cambios_guardia',
        ['funcionario_id', 'tipo_cupo', 'anio_imputacion', 'mes_imputacion'])

    op.execute("""
        INSERT INTO cupos_cambios_guardia
            (cambio_guardia_id, funcionario_id, funcionario_nombre, participante, tipo_cupo,
             fecha_referencia, anio_imputacion, mes_imputacion, uso_anticipado, usuario_registro_id,
             fecha_creacion)
        SELECT id, solicitante_funcionario_id, solicitante, 'S', tipo_cambio, fecha_cambio,
               EXTRACT(YEAR FROM fecha_cambio)::integer, EXTRACT(MONTH FROM fecha_cambio)::integer,
               false, usuario_registro_id, fecha_creacion
        FROM cambios_guardia
        WHERE tipo_cambio IN ('REEMPLAZO', 'PAGADA', 'EMERGENCIA')
        UNION ALL
        SELECT id, reemplazante_funcionario_id, reemplazante, 'R', tipo_cambio, fecha_cambio,
               EXTRACT(YEAR FROM fecha_cambio)::integer, EXTRACT(MONTH FROM fecha_cambio)::integer,
               false, usuario_registro_id, fecha_creacion
        FROM cambios_guardia
        WHERE tipo_cambio = 'REEMPLAZO'
    """)


def downgrade():
    raise RuntimeError('Los cupos históricos se conservan; no se admite una reversión destructiva automática.')
