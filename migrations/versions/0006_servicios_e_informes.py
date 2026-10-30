"""Catálogo, clasificación sin procedencia inventada e historial administrativo.

Revision ID: 0006_servicios_e_informes
Revises: 0005_guardias_fechas_y_cobertura
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0006_servicios_e_informes'
down_revision = '0005_guardias_fechas_y_cobertura'
branch_labels = depends_on = None
TABLES = ('justificativos', 'reposos', 'cambios_guardia', 'vacaciones', 'comisionados')
CATALOG = (
    ('UTI-P', 'UTI - P'), ('QUIROFANO', 'Quirófano'), ('UTI-A', 'UTI - A'),
    ('NEONATOLOGIA', 'Neonatología'), ('MATERNIDAD', 'Maternidad'), ('PAI', 'PAI'),
    ('URGE-TRAUMA', 'Urgencia Trauma'), ('SUPERVISION', 'Supervisión'), ('CIRUGIA', 'Cirugía'),
    ('CLINICA', 'Clínica'), ('PEDIATRIA_INTER', 'Pediatría Internación'), ('LAB-UMT', 'LAB - UMT'),
    ('PEDIATRIA_URGENCIA', 'Pediatría Urgencia'), ('SALUD_PUBLICA', 'Salud Pública'),
    ('PENDIENTE', 'PENDIENTE DE CLASIFICACIÓN'),
)


def upgrade():
    op.create_table('servicios', sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('nombre', sa.String(120), nullable=False), sa.Column('codigo', sa.String(40), nullable=False),
        sa.Column('activo', sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.UniqueConstraint('codigo'),
        sa.CheckConstraint('length(trim(nombre)) BETWEEN 2 AND 120', name='servicio_nombre_valido'),
        sa.CheckConstraint("codigo ~ '^[A-Z0-9][A-Z0-9_-]{1,39}$'", name='servicio_codigo_valido'))
    connection = op.get_bind()
    for code, name in CATALOG:
        connection.execute(sa.text('INSERT INTO servicios(nombre,codigo,activo) VALUES (:name,:code,:active) ON CONFLICT(codigo) DO NOTHING'),
            {'name': name, 'code': code, 'active': code != 'PENDIENTE'})
    pending = connection.execute(sa.text("SELECT id FROM servicios WHERE codigo='PENDIENTE'")).scalar_one()
    # Drenar eventos diferidos antes del DDL. Las guardias siguen siendo válidas
    # durante la clasificación; no se deshabilitan ni eliminan sus triggers.
    op.execute('SET CONSTRAINTS ALL IMMEDIATE')
    for table in TABLES:
        op.add_column(table, sa.Column('servicio_id', sa.Integer, nullable=True))
        connection.execute(sa.text(f'UPDATE {table} SET servicio_id=:id WHERE servicio_id IS NULL'), {'id': pending})
        op.alter_column(table, 'servicio_id', nullable=False)
        op.create_foreign_key(f'fk_{table}_servicio_id_servicios', table, 'servicios', ['servicio_id'], ['id'], ondelete='RESTRICT')
        op.create_index(f'ix_{table}_servicio_id', table, ['servicio_id'])
    op.create_table('historial_administrativo', sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('usuario_id', sa.Integer, sa.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('fecha_hora', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('evento', sa.String(40), nullable=False), sa.Column('entidad', sa.String(40), nullable=False),
        sa.Column('registro_id', sa.Integer),
        sa.Column('servicio_anterior_id', sa.Integer, sa.ForeignKey('servicios.id', ondelete='RESTRICT')),
        sa.Column('servicio_nuevo_id', sa.Integer, sa.ForeignKey('servicios.id', ondelete='RESTRICT')),
        sa.Column('detalles', postgresql.JSONB, nullable=False, server_default='{}'))
    op.create_index('ix_historial_administrativo_fecha_hora', 'historial_administrativo', ['fecha_hora'])
    # Los antiguos pueden seguir pendientes; ningún INSERT nuevo puede usar ese comodín.
    op.execute('''CREATE FUNCTION validar_servicio_registro() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE allowed boolean;
    BEGIN
        IF TG_OP = 'UPDATE' THEN
            IF NEW.servicio_id IS NOT DISTINCT FROM OLD.servicio_id THEN RETURN NEW; END IF;
        END IF;
        SELECT activo AND codigo <> 'PENDIENTE' INTO allowed FROM servicios WHERE id=NEW.servicio_id FOR SHARE;
        IF allowed IS DISTINCT FROM TRUE THEN
            RAISE EXCEPTION 'Selecciona un servicio hospitalario activo' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
    END $$''')
    for table in TABLES:
        op.execute(f'CREATE TRIGGER validar_servicio_{table} BEFORE INSERT OR UPDATE OF servicio_id ON {table} FOR EACH ROW EXECUTE FUNCTION validar_servicio_registro()')
    # Un catálogo es permanente: desactivar preserva su identidad y las FKs.
    op.execute('''CREATE FUNCTION proteger_catalogo_servicios() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP IN ('DELETE', 'TRUNCATE') THEN RAISE EXCEPTION 'El catálogo se desactiva, no se elimina'; END IF;
        IF NEW.codigo IS DISTINCT FROM OLD.codigo OR OLD.codigo='PENDIENTE' THEN
            RAISE EXCEPTION 'La identidad del servicio es permanente';
        END IF;
        RETURN NEW;
    END $$''')
    op.execute('CREATE TRIGGER proteger_catalogo BEFORE UPDATE OR DELETE ON servicios FOR EACH ROW EXECUTE FUNCTION proteger_catalogo_servicios()')
    op.execute('CREATE TRIGGER proteger_catalogo_truncate BEFORE TRUNCATE ON servicios FOR EACH STATEMENT EXECUTE FUNCTION proteger_catalogo_servicios()')
    op.execute('SET CONSTRAINTS ALL DEFERRED')


def downgrade():
    raise RuntimeError('Migración de conservación: no se eliminan clasificaciones ni historial. Restaura un respaldo revisado si fuera necesario.')
