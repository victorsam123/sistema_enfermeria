"""Adjuntos privados con propietarios y auditoría verificables.

Revision ID: 0008_documentos_adjuntos
Revises: 0007_usuarios_roles_eliminacion
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0008_documentos_adjuntos'
down_revision = '0007_usuarios_roles_eliminacion'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('documentos_adjuntos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tipo_modulo', sa.String(20), nullable=False),
        sa.Column('registro_id', sa.Integer(), nullable=False),
        sa.Column('justificativo_id', sa.Integer(), sa.ForeignKey('justificativos.id', ondelete='RESTRICT')),
        sa.Column('reposo_id', sa.Integer(), sa.ForeignKey('reposos.id', ondelete='RESTRICT')),
        sa.Column('cambio_guardia_id', sa.Integer(), sa.ForeignKey('cambios_guardia.id', ondelete='RESTRICT')),
        sa.Column('vacacion_id', sa.Integer(), sa.ForeignKey('vacaciones.id', ondelete='RESTRICT')),
        sa.Column('comisionado_id', sa.Integer(), sa.ForeignKey('comisionados.id', ondelete='RESTRICT')),
        sa.Column('nombre_original', sa.String(180), nullable=False),
        sa.Column('nombre_almacenamiento', sa.String(100), nullable=False, unique=True),
        sa.Column('tipo_mime', sa.String(40), nullable=False),
        sa.Column('tamano_bytes', sa.Integer(), nullable=False),
        sa.Column('ruta_almacenamiento', sa.String(160), nullable=False, unique=True),
        sa.Column('ruta_vista', sa.String(160), nullable=False, unique=True),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('sha256_vista', sa.String(64), nullable=False),
        sa.Column('almacenamiento', sa.String(10), nullable=False),
        sa.Column('lote_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('orden_lote', sa.Integer(), nullable=False),
        sa.Column('usuario_carga_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('fecha_carga', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('fecha_retiro', sa.DateTime(timezone=True)),
        sa.Column('usuario_retiro_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='RESTRICT')),
        sa.Column('motivo_retiro', sa.String(1000)),
        sa.CheckConstraint("""num_nonnulls(justificativo_id,reposo_id,cambio_guardia_id,vacacion_id,comisionado_id)=1 AND (
            (tipo_modulo='justificativos' AND justificativo_id=registro_id) OR
            (tipo_modulo='reposos' AND reposo_id=registro_id) OR
            (tipo_modulo IN ('guardias','pagadas') AND cambio_guardia_id=registro_id) OR
            (tipo_modulo='vacaciones' AND vacacion_id=registro_id) OR
            (tipo_modulo='comisionados' AND comisionado_id=registro_id)) IS TRUE""", name='documento_propietario_unico'),
        sa.CheckConstraint("tipo_mime IN ('image/jpeg','image/png','image/webp') AND tamano_bytes>0", name='documento_imagen_valida'),
        sa.CheckConstraint("almacenamiento IN ('local','s3') AND orden_lote>=0", name='documento_almacenamiento_valido'),
        sa.CheckConstraint("sha256 ~ '^[a-f0-9]{64}$' AND sha256_vista ~ '^[a-f0-9]{64}$'", name='documento_hash_valido'),
        sa.CheckConstraint("(activo AND fecha_retiro IS NULL AND usuario_retiro_id IS NULL AND motivo_retiro IS NULL) OR (NOT activo AND fecha_retiro IS NOT NULL AND usuario_retiro_id IS NOT NULL AND motivo_retiro IS NOT NULL AND length(trim(motivo_retiro)) BETWEEN 3 AND 1000)", name='documento_retiro_auditado'),
        sa.UniqueConstraint('tipo_modulo', 'registro_id', 'lote_id', 'orden_lote', name='documento_envio_unico'))
    op.create_index('ix_documentos_registro_activo', 'documentos_adjuntos', ['tipo_modulo', 'registro_id', 'activo'])
    op.execute("""
    CREATE FUNCTION proteger_asociacion_documento() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE categoria text; borrado boolean;
    BEGIN
      IF TG_OP='UPDATE' AND
        (to_jsonb(NEW)-ARRAY['activo','fecha_retiro','usuario_retiro_id','motivo_retiro']) IS DISTINCT FROM
        (to_jsonb(OLD)-ARRAY['activo','fecha_retiro','usuario_retiro_id','motivo_retiro']) THEN
        RAISE EXCEPTION 'La asociación y los datos originales del documento son inmutables';
      END IF;
      IF TG_OP='UPDATE' AND NOT OLD.activo AND NEW IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'Un documento retirado conserva su historial';
      END IF;
      IF NEW.cambio_guardia_id IS NOT NULL THEN
        SELECT tipo_cambio,eliminado INTO categoria,borrado FROM cambios_guardia WHERE id=NEW.cambio_guardia_id FOR UPDATE;
        IF categoria IS DISTINCT FROM (CASE NEW.tipo_modulo WHEN 'guardias' THEN 'NORMAL' WHEN 'pagadas' THEN 'PAGADA' END) THEN
          RAISE EXCEPTION 'Categoría de cambio de guardia incorrecta para el adjunto';
        END IF;
      ELSIF NEW.justificativo_id IS NOT NULL THEN
        SELECT eliminado INTO borrado FROM justificativos WHERE id=NEW.justificativo_id FOR UPDATE;
      ELSIF NEW.reposo_id IS NOT NULL THEN
        SELECT eliminado INTO borrado FROM reposos WHERE id=NEW.reposo_id FOR UPDATE;
      ELSIF NEW.vacacion_id IS NOT NULL THEN
        SELECT eliminado INTO borrado FROM vacaciones WHERE id=NEW.vacacion_id FOR UPDATE;
      ELSIF NEW.comisionado_id IS NOT NULL THEN
        SELECT eliminado INTO borrado FROM comisionados WHERE id=NEW.comisionado_id FOR UPDATE;
      END IF;
      IF TG_OP='INSERT' AND borrado IS TRUE THEN RAISE EXCEPTION 'Registro eliminado'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER documento_asociacion_protegida BEFORE INSERT OR UPDATE ON documentos_adjuntos
      FOR EACH ROW EXECUTE FUNCTION proteger_asociacion_documento();
    CREATE FUNCTION conservar_tipo_guardia_documentada() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.tipo_cambio IS DISTINCT FROM OLD.tipo_cambio AND EXISTS
        (SELECT 1 FROM documentos_adjuntos WHERE cambio_guardia_id=OLD.id) THEN
        RAISE EXCEPTION 'No se puede cambiar la categoría de una guardia documentada';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER guardia_categoria_documentada BEFORE UPDATE OF tipo_cambio ON cambios_guardia
      FOR EACH ROW EXECUTE FUNCTION conservar_tipo_guardia_documentada();
    """)


def downgrade():
    raise RuntimeError('Los adjuntos e historiales se conservan. No se admite una reversión destructiva automática.')
