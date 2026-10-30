"""Añade carrera para planillas de vacaciones.

Revision ID: 0011_carrera_funcionarios
Revises: 0010_vinculos_laborales
"""
from alembic import op
import sqlalchemy as sa

revision = '0011_carrera_funcionarios'
down_revision = '0010_vinculos_laborales'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('funcionarios', sa.Column('carrera', sa.String(length=80), nullable=True))
    op.create_check_constraint('funcionario_carrera_valida', 'funcionarios',
        "carrera IS NULL OR carrera IN ('LIC. EN ENFERMERIA','TEC. EN ENFERMERIA','AUX. EN ENFERMERA','CAMILLERO')")


def downgrade():
    raise RuntimeError('Las carreras registradas se conservan. No se admite una reversión destructiva automática.')
