"""Archivo privado de notas emitidas; no modifica las tablas anteriores."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0013_notas_compensatorias'
down_revision = '0012_guardias_intercambio'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('notas_compensatorias',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('numero', sa.Integer(), nullable=False),
        sa.Column('anio', sa.Integer(), nullable=False),
        sa.Column('fecha_emision', sa.Date(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('solicitud_id', sa.Uuid(), nullable=False, unique=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('registros', JSONB(), nullable=False),
        sa.Column('plantilla_sha256', sa.String(64), nullable=False),
        sa.Column('documento_sha256', sa.String(64), nullable=False),
        sa.Column('pdf_sha256', sa.String(64), nullable=False),
        sa.Column('documento', sa.LargeBinary(), nullable=False),
        sa.Column('pdf', sa.LargeBinary(), nullable=False),
        sa.UniqueConstraint('anio', 'numero', name='nota_numero_anual_unico'),
        sa.CheckConstraint('numero > 0 AND anio=EXTRACT(YEAR FROM fecha_emision)', name='nota_identificacion_valida'),
        sa.CheckConstraint("jsonb_typeof(registros)='array' AND jsonb_array_length(registros)>0", name='nota_registros_requeridos'))
    op.execute("""CREATE FUNCTION conservar_nota_emitida() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Una nota emitida conserva su documento, número e historial'; END $$;
        CREATE TRIGGER nota_emitida_inmutable BEFORE UPDATE OR DELETE ON notas_compensatorias
        FOR EACH ROW EXECUTE FUNCTION conservar_nota_emitida();""")


def downgrade():
    raise RuntimeError('Las notas emitidas y sus documentos se conservan; no se admite una reversión destructiva.')
