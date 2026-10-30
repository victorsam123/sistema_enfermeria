"""Fechas independientes de guardia y cobertura opcional, conservando lo anterior."""
from alembic import op
import sqlalchemy as sa

revision = '0005_guardias_fechas_y_cobertura'
down_revision = '0004_reposos'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('justificativos', 'fecha_cobertura', existing_type=sa.Date(), nullable=True)
    op.add_column('cambios_guardia', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('cambios_guardia', sa.Column('usuario_modificacion_id', sa.Integer(),
        sa.ForeignKey('usuarios.id', name='fk_guardia_editor', ondelete='RESTRICT')))
    op.create_table('detalles_cambio_guardia',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cambio_guardia_id', sa.Integer(), sa.ForeignKey('cambios_guardia.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('participante', sa.String(1), nullable=False),
        sa.Column('funcionario', sa.String(180), nullable=False),
        sa.Column('fecha_guardia', sa.Date(), nullable=False),
        sa.Column('hora_inicio', sa.Time(), nullable=False),
        sa.Column('hora_fin', sa.Time(), nullable=False),
        sa.Column('codigo', sa.String(1)),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.CheckConstraint("participante IN ('S', 'R')", name='detalle_participante_valido'),
        sa.CheckConstraint("codigo IS NULL OR codigo IN ('G', 'L', 'S', 'R')", name='detalle_codigo_valido'),
        sa.CheckConstraint('hora_inicio <> hora_fin', name='detalle_horario_definido'),
        sa.CheckConstraint('orden >= 0', name='detalle_orden_valido'),
        sa.UniqueConstraint('cambio_guardia_id', 'orden', name='uq_detalle_guardia_orden'),
        sa.UniqueConstraint('cambio_guardia_id', 'participante', 'fecha_guardia', 'hora_inicio', 'hora_fin', 'codigo',
            name='uq_detalle_guardia_evento', deferrable=True, initially='DEFERRED', postgresql_nulls_not_distinct=True))
    op.create_index('ix_detalles_cambio_guardia_fecha_guardia', 'detalles_cambio_guardia', ['fecha_guardia'])
    # Los dos participantes ya figuraban en cada registro anterior. Ambos
    # conservan exactamente su fecha y horario anteriores; no se infiere G/L.
    op.execute('''
        INSERT INTO detalles_cambio_guardia
            (cambio_guardia_id, participante, funcionario, fecha_guardia, hora_inicio, hora_fin, codigo, orden)
        SELECT id, 'S', solicitante, fecha_cambio, hora_inicio, hora_fin, 'S', 0 FROM cambios_guardia
        UNION ALL
        SELECT id, 'R', reemplazante, fecha_cambio, hora_inicio, hora_fin, 'R', 1 FROM cambios_guardia;
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM cambios_guardia c WHERE
                (SELECT count(*) FROM detalles_cambio_guardia d WHERE d.cambio_guardia_id=c.id) <> 2
                OR NOT EXISTS (SELECT 1 FROM detalles_cambio_guardia d WHERE d.cambio_guardia_id=c.id
                    AND d.participante='S' AND d.funcionario=c.solicitante AND d.fecha_guardia=c.fecha_cambio
                    AND d.hora_inicio=c.hora_inicio AND d.hora_fin=c.hora_fin)
                OR NOT EXISTS (SELECT 1 FROM detalles_cambio_guardia d WHERE d.cambio_guardia_id=c.id
                    AND d.participante='R' AND d.funcionario=c.reemplazante AND d.fecha_guardia=c.fecha_cambio
                    AND d.hora_inicio=c.hora_inicio AND d.hora_fin=c.hora_fin))
            THEN RAISE EXCEPTION 'Migración de fechas de guardia incompleta'; END IF;
        END $$;
    ''')
    # Barrera transaccional: se verifica al terminar toda la operación, para
    # poder actualizar ambos participantes y sus fechas de forma atómica.
    op.execute('''
        CREATE FUNCTION validar_operacion_guardia() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE target_id integer; parent cambios_guardia%ROWTYPE;
        BEGIN
            IF TG_TABLE_NAME='cambios_guardia' THEN target_id=NEW.id;
            ELSIF TG_OP='DELETE' THEN target_id=OLD.cambio_guardia_id;
            ELSE target_id=NEW.cambio_guardia_id; END IF;
            SELECT * INTO parent FROM cambios_guardia WHERE id=target_id;
            IF NOT FOUND THEN RETURN NULL; END IF;
            IF NOT EXISTS (SELECT 1 FROM detalles_cambio_guardia WHERE cambio_guardia_id=target_id AND participante='S')
               OR NOT EXISTS (SELECT 1 FROM detalles_cambio_guardia WHERE cambio_guardia_id=target_id AND participante='R')
               OR EXISTS (SELECT 1 FROM detalles_cambio_guardia WHERE cambio_guardia_id=target_id
                    AND funcionario IS DISTINCT FROM CASE participante WHEN 'S' THEN parent.solicitante ELSE parent.reemplazante END)
            THEN RAISE EXCEPTION 'Cada cambio requiere fechas coherentes para ambos funcionarios' USING ERRCODE='23514'; END IF;
            RETURN NULL;
        END $$;
        CREATE CONSTRAINT TRIGGER guardia_detalles_coherentes AFTER INSERT OR UPDATE ON cambios_guardia
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validar_operacion_guardia();
        CREATE CONSTRAINT TRIGGER detalle_guardia_coherente AFTER INSERT OR UPDATE OR DELETE ON detalles_cambio_guardia
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validar_operacion_guardia();
    ''')


def downgrade():
    raise RuntimeError('Reversión destructiva bloqueada: conservar detalles, cambios y justificativos. Crear una migración correctiva.')
