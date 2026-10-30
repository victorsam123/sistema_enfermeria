"""Vínculos independientes dentro de la misma ficha.

Revision ID: 0010_vinculos_laborales
Revises: 0009_funcionarios
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0010_vinculos_laborales'
down_revision = '0009_funcionarios'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('LOCK TABLE funcionarios IN ACCESS EXCLUSIVE MODE')
    op.add_column('funcionarios', sa.Column('cantidad_vinculos_declarada', sa.Integer()))
    op.create_check_constraint('funcionario_declaracion_historica_valida', 'funcionarios',
        'cantidad_vinculos_declarada IS NULL OR cantidad_vinculos_declarada>=0')
    op.alter_column('funcionarios', 'cantidad_vinculos', server_default='0', existing_type=sa.Integer(), existing_nullable=False)
    op.create_table('vinculos_laborales',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('funcionario_id', sa.Integer(), sa.ForeignKey('funcionarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('numero_vinculo', sa.Integer(), nullable=False),
        sa.Column('fecha_ingreso', sa.Date(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('usuario_registro_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('usuario_modificacion_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='RESTRICT')),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('fecha_modificacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('motivo_estado', sa.String(1000)),
        sa.Column('solicitud_id', postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.UniqueConstraint('funcionario_id', 'numero_vinculo', name='uq_vinculo_numero_funcionario'),
        sa.CheckConstraint('numero_vinculo>0', name='vinculo_numero_positivo'),
        sa.CheckConstraint('activo OR (motivo_estado IS NOT NULL AND length(trim(motivo_estado)) BETWEEN 3 AND 1000)', name='vinculo_estado_justificado'))
    op.create_index('ix_vinculos_laborales_funcionario_id', 'vinculos_laborales', ['funcionario_id'])
    # La fecha es evidencia para UN vínculo; el contador no prueba otras fechas.
    op.execute("""
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM funcionarios WHERE fecha_ingreso IS NULL OR fecha_ingreso<fecha_nacimiento OR
        fecha_ingreso>(CURRENT_TIMESTAMP AT TIME ZONE 'America/Asuncion')::date) THEN
        RAISE EXCEPTION 'Revisa las fechas iniciales antes de migrar; no se inventarán fechas';
      END IF;
    END $$;
    UPDATE funcionarios SET cantidad_vinculos_declarada=cantidad_vinculos;
    INSERT INTO vinculos_laborales(funcionario_id,numero_vinculo,fecha_ingreso,activo,
      usuario_registro_id,usuario_modificacion_id,fecha_creacion,fecha_modificacion,solicitud_id)
    SELECT id,1,fecha_ingreso,true,usuario_registro_id,usuario_modificacion_id,
      fecha_creacion,fecha_modificacion,gen_random_uuid() FROM funcionarios;
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM funcionarios f WHERE NOT EXISTS
        (SELECT 1 FROM vinculos_laborales v WHERE v.funcionario_id=f.id AND v.numero_vinculo=1 AND v.fecha_ingreso=f.fecha_ingreso)) THEN
        RAISE EXCEPTION 'No se verificó la migración de la fecha inicial';
      END IF;
    END $$;
    UPDATE funcionarios f SET cantidad_vinculos=(SELECT count(*) FROM vinculos_laborales v WHERE v.funcionario_id=f.id AND v.activo);
    INSERT INTO historial_administrativo(usuario_id,evento,entidad,registro_id,detalles)
    SELECT usuario_registro_id,'MIGRACION_VINCULO_INICIAL','funcionarios',id,
      jsonb_build_object('vinculo_id',(SELECT id FROM vinculos_laborales WHERE funcionario_id=f.id AND numero_vinculo=1),
        'numero_vinculo',1,'fecha_ingreso_anterior',NULL,'fecha_ingreso_nueva',fecha_ingreso,
        'cantidad_declarada',cantidad_vinculos_declarada,'cantidad_activa',cantidad_vinculos) FROM funcionarios f;
    """)
    op.create_table('documentos_vinculos_laborales',
        sa.Column('documento_id', sa.Integer(), sa.ForeignKey('documentos_adjuntos.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('vinculo_laboral_id', sa.Integer(), sa.ForeignKey('vinculos_laborales.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('usuario_asignacion_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('fecha_asignacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.execute("""
    CREATE FUNCTION validar_vinculo_laboral() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE nacimiento date; siguiente integer;
    BEGIN
      SELECT fecha_nacimiento INTO nacimiento FROM funcionarios WHERE id=NEW.funcionario_id FOR UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'Ficha inexistente'; END IF;
      IF NEW.fecha_ingreso<nacimiento OR NEW.fecha_ingreso>(CURRENT_TIMESTAMP AT TIME ZONE 'America/Asuncion')::date THEN
        RAISE EXCEPTION 'Fecha de vínculo no válida';
      END IF;
      IF TG_OP='INSERT' THEN
        SELECT coalesce(max(numero_vinculo),0)+1 INTO siguiente FROM vinculos_laborales WHERE funcionario_id=NEW.funcionario_id;
        IF NEW.numero_vinculo<>siguiente THEN RAISE EXCEPTION 'El número del vínculo se asigna en orden'; END IF;
      ELSE
        IF (NEW.id,NEW.funcionario_id,NEW.numero_vinculo,NEW.solicitud_id,NEW.usuario_registro_id,NEW.fecha_creacion) IS DISTINCT FROM
           (OLD.id,OLD.funcionario_id,OLD.numero_vinculo,OLD.solicitud_id,OLD.usuario_registro_id,OLD.fecha_creacion) THEN
          RAISE EXCEPTION 'La identidad y auditoría inicial del vínculo se conservan';
        END IF;
        IF NEW.usuario_modificacion_id IS NULL THEN RAISE EXCEPTION 'Indica el usuario responsable'; END IF;
        IF NEW.activo IS DISTINCT FROM OLD.activo AND (NEW.motivo_estado IS NULL OR length(trim(NEW.motivo_estado)) NOT BETWEEN 3 AND 1000) THEN
          RAISE EXCEPTION 'Indica el motivo del cambio de estado';
        END IF;
        NEW.version:=OLD.version+1;
        NEW.fecha_modificacion:=clock_timestamp();
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER vinculo_validado BEFORE INSERT OR UPDATE ON vinculos_laborales
      FOR EACH ROW EXECUTE FUNCTION validar_vinculo_laboral();

    CREATE FUNCTION auditar_y_contar_vinculo() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE actor integer; evento text; fecha_anterior date; estado_anterior boolean;
    BEGIN
      IF TG_OP='INSERT' THEN actor:=NEW.usuario_registro_id; evento:='VINCULO_CREADO';
      ELSE
        actor:=NEW.usuario_modificacion_id; fecha_anterior:=OLD.fecha_ingreso; estado_anterior:=OLD.activo;
        evento:=CASE WHEN NEW.activo IS DISTINCT FROM OLD.activo THEN
          CASE WHEN NEW.activo THEN 'VINCULO_REACTIVADO' ELSE 'VINCULO_DESACTIVADO' END ELSE 'VINCULO_MODIFICADO' END;
      END IF;
      UPDATE funcionarios f SET cantidad_vinculos=(SELECT count(*) FROM vinculos_laborales v WHERE v.funcionario_id=f.id AND v.activo),
        usuario_modificacion_id=actor,fecha_modificacion=clock_timestamp(),version=f.version+1 WHERE f.id=NEW.funcionario_id;
      INSERT INTO historial_administrativo(usuario_id,evento,entidad,registro_id,detalles) VALUES
        (actor,evento,'funcionarios',NEW.funcionario_id,jsonb_build_object('vinculo_id',NEW.id,'numero_vinculo',NEW.numero_vinculo,
        'fecha_ingreso_anterior',fecha_anterior,'fecha_ingreso_nueva',NEW.fecha_ingreso,
        'activo_anterior',estado_anterior,'activo_nuevo',NEW.activo,'motivo',NEW.motivo_estado));
      RETURN NULL;
    END $$;
    CREATE TRIGGER vinculo_auditado AFTER INSERT OR UPDATE ON vinculos_laborales
      FOR EACH ROW EXECUTE FUNCTION auditar_y_contar_vinculo();

    CREATE FUNCTION verificar_total_vinculos() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE real_total integer; actual integer;
    BEGIN
      SELECT cantidad_vinculos INTO actual FROM funcionarios WHERE id=NEW.id;
      IF NOT FOUND THEN RETURN NULL; END IF;
      SELECT count(*) INTO real_total FROM vinculos_laborales WHERE funcionario_id=NEW.id AND activo;
      IF actual<>real_total THEN RAISE EXCEPTION 'El total se calcula a partir de los vínculos activos'; END IF;
      RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER funcionario_total_vinculos AFTER INSERT OR UPDATE ON funcionarios
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION verificar_total_vinculos();

    CREATE FUNCTION conservar_referencia_laboral() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='UPDATE' AND (NEW.fecha_ingreso,NEW.cantidad_vinculos_declarada) IS DISTINCT FROM (OLD.fecha_ingreso,OLD.cantidad_vinculos_declarada) THEN
        RAISE EXCEPTION 'La referencia inicial se conserva; edita la fecha en el vínculo correspondiente';
      END IF;
      IF EXISTS(SELECT 1 FROM vinculos_laborales WHERE funcionario_id=NEW.id AND fecha_ingreso<NEW.fecha_nacimiento) THEN
        RAISE EXCEPTION 'El nacimiento no puede ser posterior a las fechas laborales registradas';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER funcionario_referencia_laboral BEFORE UPDATE ON funcionarios
      FOR EACH ROW EXECUTE FUNCTION conservar_referencia_laboral();
    CREATE FUNCTION conservar_vinculos_laborales() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Los vínculos se desactivan; no se eliminan físicamente'; END $$;
    CREATE TRIGGER vinculo_no_delete BEFORE DELETE ON vinculos_laborales
      FOR EACH ROW EXECUTE FUNCTION conservar_vinculos_laborales();
    CREATE TRIGGER vinculo_no_truncate BEFORE TRUNCATE ON vinculos_laborales
      FOR EACH STATEMENT EXECUTE FUNCTION conservar_vinculos_laborales();

    CREATE FUNCTION validar_documento_vinculo() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE funcionario integer; valido boolean;
    BEGIN
      SELECT funcionario_id INTO funcionario FROM vinculos_laborales WHERE id=NEW.vinculo_laboral_id;
      SELECT (d.funcionario_id=funcionario OR
        EXISTS(SELECT 1 FROM justificativos WHERE id=d.justificativo_id AND funcionario_id=funcionario) OR
        EXISTS(SELECT 1 FROM reposos WHERE id=d.reposo_id AND funcionario_id=funcionario) OR
        EXISTS(SELECT 1 FROM vacaciones WHERE id=d.vacacion_id AND funcionario_id=funcionario) OR
        EXISTS(SELECT 1 FROM comisionados WHERE id=d.comisionado_id AND funcionario_id=funcionario) OR
        EXISTS(SELECT 1 FROM cambios_guardia WHERE id=d.cambio_guardia_id AND
          (solicitante_funcionario_id=funcionario OR reemplazante_funcionario_id=funcionario))) INTO valido
        FROM documentos_adjuntos d WHERE d.id=NEW.documento_id;
      IF valido IS DISTINCT FROM true THEN RAISE EXCEPTION 'El documento y el vínculo deben corresponder a la misma ficha'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER documento_vinculo_propietario BEFORE INSERT OR UPDATE ON documentos_vinculos_laborales
      FOR EACH ROW EXECUTE FUNCTION validar_documento_vinculo();
    """)


def downgrade():
    raise RuntimeError('Los vínculos y sus historiales se conservan. No se admite una reversión destructiva automática.')
