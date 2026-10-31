"""Nuevas categorías, conservando operaciones, detalles y adjuntos históricos.

Revision ID: 0012_guardias_intercambio
Revises: 0011_carrera_funcionarios
"""
from alembic import op

revision = '0012_guardias_intercambio'
down_revision = '0011_carrera_funcionarios'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('cambio_tipo_valido', 'cambios_guardia', type_='check')
    op.create_check_constraint('cambio_tipo_valido', 'cambios_guardia',
        "tipo_cambio IN ('NORMAL', 'PAGADA', 'REEMPLAZO', 'EMERGENCIA')")
    op.drop_constraint('documento_propietario_unico', 'documentos_adjuntos', type_='check')
    op.create_check_constraint('documento_propietario_unico', 'documentos_adjuntos', """
num_nonnulls(justificativo_id,reposo_id,cambio_guardia_id,vacacion_id,comisionado_id,funcionario_id)=1 AND (
 (tipo_modulo='justificativos' AND justificativo_id=registro_id) OR
 (tipo_modulo='reposos' AND reposo_id=registro_id) OR
 (tipo_modulo IN ('guardias','pagadas','reemplazos','emergencias') AND cambio_guardia_id=registro_id) OR
 (tipo_modulo='vacaciones' AND vacacion_id=registro_id) OR
 (tipo_modulo='comisionados' AND comisionado_id=registro_id) OR
 (tipo_modulo='funcionarios' AND funcionario_id=registro_id)) IS TRUE
    """)
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
        IF categoria IS DISTINCT FROM (CASE NEW.tipo_modulo WHEN 'guardias' THEN 'NORMAL' WHEN 'pagadas' THEN 'PAGADA' WHEN 'reemplazos' THEN 'REEMPLAZO' WHEN 'emergencias' THEN 'EMERGENCIA' END) THEN
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
    """)


def downgrade():
    raise RuntimeError('Los intercambios y documentos históricos se conservan; no se admite una reversión destructiva automática.')
