"""Fichas únicas, fotografía privada y vínculos opcionales sin backfill.

Revision ID: 0009_funcionarios
Revises: 0008_documentos_adjuntos
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0009_funcionarios'
down_revision = '0008_documentos_adjuntos'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('funcionarios',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nombres', sa.String(120), nullable=False),
        sa.Column('apellidos', sa.String(120), nullable=False),
        sa.Column('cedula', sa.String(12), nullable=False, unique=True),
        sa.Column('fecha_nacimiento', sa.Date(), nullable=False),
        sa.Column('fecha_ingreso', sa.Date(), nullable=False),
        sa.Column('cantidad_vinculos', sa.Integer(), nullable=False),
        sa.Column('direccion_actual', sa.String(500), nullable=False),
        sa.Column('servicio_id', sa.Integer(), sa.ForeignKey('servicios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('foto_ruta', sa.String(160)),
        sa.Column('usuario_registro_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('usuario_modificacion_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='RESTRICT')),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('fecha_modificacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('solicitud_id', postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.CheckConstraint("cedula ~ '^[1-9][0-9]{0,11}$'", name='funcionario_cedula_normalizada'),
        sa.CheckConstraint('cantidad_vinculos>=0', name='funcionario_vinculos_no_negativos'),
        sa.CheckConstraint('fecha_ingreso>=fecha_nacimiento', name='funcionario_fechas_coherentes'),
        sa.CheckConstraint("length(trim(nombres))>0 AND length(trim(apellidos))>0 AND length(nombres || ' ' || apellidos)<=180 AND length(trim(direccion_actual))>0", name='funcionario_datos_completos'))
    op.create_index('ix_funcionarios_servicio_id', 'funcionarios', ['servicio_id'])
    op.create_foreign_key('fk_funcionario_foto', 'funcionarios', 'documentos_adjuntos', ['foto_ruta'], ['ruta_vista'],
                          ondelete='RESTRICT', deferrable=True, initially='DEFERRED')
    op.add_column('documentos_adjuntos', sa.Column('funcionario_id', sa.Integer(), sa.ForeignKey('funcionarios.id', name='fk_documento_funcionario', ondelete='RESTRICT')))
    op.drop_constraint('documento_propietario_unico', 'documentos_adjuntos', type_='check')
    op.create_check_constraint('documento_propietario_unico', 'documentos_adjuntos', """
        num_nonnulls(justificativo_id,reposo_id,cambio_guardia_id,vacacion_id,comisionado_id,funcionario_id)=1 AND (
        (tipo_modulo='justificativos' AND justificativo_id=registro_id) OR
        (tipo_modulo='reposos' AND reposo_id=registro_id) OR
        (tipo_modulo IN ('guardias','pagadas') AND cambio_guardia_id=registro_id) OR
        (tipo_modulo='vacaciones' AND vacacion_id=registro_id) OR
        (tipo_modulo='comisionados' AND comisionado_id=registro_id) OR
        (tipo_modulo='funcionarios' AND funcionario_id=registro_id)) IS TRUE""")
    op.create_index('uq_funcionario_foto_activa', 'documentos_adjuntos', ['funcionario_id'], unique=True,
                    postgresql_where=sa.text('funcionario_id IS NOT NULL AND activo'))
    for table in ('justificativos', 'reposos', 'vacaciones', 'comisionados'):
        op.add_column(table, sa.Column('funcionario_id', sa.Integer(), sa.ForeignKey('funcionarios.id', name=f'fk_{table}_funcionario', ondelete='RESTRICT')))
    for participant in ('solicitante', 'reemplazante'):
        op.add_column('cambios_guardia', sa.Column(participant + '_funcionario_id', sa.Integer(),
            sa.ForeignKey('funcionarios.id', name=f'fk_guardia_{participant}_funcionario', ondelete='RESTRICT')))
    op.create_check_constraint('guardia_fichas_distintas', 'cambios_guardia',
        'solicitante_funcionario_id IS NULL OR reemplazante_funcionario_id IS NULL OR solicitante_funcionario_id<>reemplazante_funcionario_id')
    op.execute("""
    CREATE OR REPLACE FUNCTION proteger_asociacion_documento() RETURNS trigger LANGUAGE plpgsql AS $$
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
      ELSIF NEW.funcionario_id IS NOT NULL THEN
        PERFORM id FROM funcionarios WHERE id=NEW.funcionario_id FOR UPDATE;
      END IF;
      IF TG_OP='INSERT' AND borrado IS TRUE THEN RAISE EXCEPTION 'Registro eliminado'; END IF;
      RETURN NEW;
    END $$;
    CREATE FUNCTION comprobar_foto_funcionario() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE fid integer; ruta text; cantidad integer;
    BEGIN
      IF TG_TABLE_NAME='funcionarios' THEN fid:=NEW.id;
      ELSE fid:=CASE WHEN TG_OP='DELETE' THEN OLD.funcionario_id ELSE NEW.funcionario_id END; END IF;
      IF fid IS NULL THEN RETURN NULL; END IF;
      SELECT foto_ruta INTO ruta FROM funcionarios WHERE id=fid;
      IF NOT FOUND THEN RETURN NULL; END IF;
      SELECT count(*) INTO cantidad FROM documentos_adjuntos WHERE funcionario_id=fid AND activo;
      IF (ruta IS NULL AND cantidad<>0) OR (ruta IS NOT NULL AND (cantidad<>1 OR NOT EXISTS
         (SELECT 1 FROM documentos_adjuntos WHERE funcionario_id=fid AND activo AND ruta_vista=ruta AND tipo_modulo='funcionarios'))) THEN
        RAISE EXCEPTION 'La fotografía no pertenece a la ficha o no está activa';
      END IF;
      RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER funcionario_foto_coherente AFTER INSERT OR UPDATE ON funcionarios
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION comprobar_foto_funcionario();
    CREATE CONSTRAINT TRIGGER documento_foto_coherente AFTER INSERT OR UPDATE OR DELETE ON documentos_adjuntos
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION comprobar_foto_funcionario();
    CREATE FUNCTION validar_ficha_funcionario() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.fecha_nacimiento>(CURRENT_TIMESTAMP AT TIME ZONE 'America/Asuncion')::date OR
         NEW.fecha_ingreso>(CURRENT_TIMESTAMP AT TIME ZONE 'America/Asuncion')::date THEN
        RAISE EXCEPTION 'Las fechas de la ficha no pueden ser futuras';
      END IF;
      IF TG_OP='UPDATE' AND (NEW.id<>OLD.id OR NEW.solicitud_id<>OLD.solicitud_id OR
         NEW.usuario_registro_id<>OLD.usuario_registro_id OR NEW.fecha_creacion<>OLD.fecha_creacion) THEN
        RAISE EXCEPTION 'La identidad y la auditoría inicial de la ficha se conservan';
      END IF;
      IF (TG_OP='INSERT' OR NEW.servicio_id IS DISTINCT FROM OLD.servicio_id) AND NOT EXISTS
         (SELECT 1 FROM servicios WHERE id=NEW.servicio_id AND activo AND codigo<>'PENDIENTE') THEN
        RAISE EXCEPTION 'Selecciona un servicio activo';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER funcionario_datos_validos BEFORE INSERT OR UPDATE ON funcionarios
      FOR EACH ROW EXECUTE FUNCTION validar_ficha_funcionario();
    """)


def downgrade():
    raise RuntimeError('Las fichas, fotografías y relaciones se conservan. No se admite una reversión destructiva automática.')
