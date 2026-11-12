"""Add an optional WhatsApp phone number to employee records."""
from alembic import op
import sqlalchemy as sa


revision = '0015_telefono_funcionarios'
down_revision = '0014_guardia_cupos_anticipados'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('funcionarios', sa.Column('telefono', sa.String(length=15), nullable=True))
    op.create_check_constraint('funcionario_telefono_valido', 'funcionarios',
        "telefono IS NULL OR telefono ~ '^[0-9]{8,15}$'")


def downgrade():
    op.drop_constraint('funcionario_telefono_valido', 'funcionarios', type_='check')
    op.drop_column('funcionarios', 'telefono')
