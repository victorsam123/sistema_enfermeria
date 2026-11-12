"""Respalda y añade notas oficiales sin reescribir registros. Servidor detenido."""
from datetime import datetime
from pathlib import Path
from flask_migrate import upgrade
from app import create_app
from app.extensions import db
from scripts.respaldar_documentos import main as backup


def main():
    app = create_app()
    with app.app_context():
        revision = db.session.scalar(db.text('SELECT version_num FROM alembic_version'))
        if revision == '0013_notas_compensatorias':
            print('Actualización 13 ya aplicada. No se modificaron los datos.')
            return
        if revision != '0012_guardias_intercambio':
            raise RuntimeError('Se requiere la revisión 0012_guardias_intercambio. Aplica primero las actualizaciones anteriores con su respaldo.')
        inspector = db.inspect(db.engine)
        quote = db.engine.dialect.identifier_preparer.quote
        snapshots = {}
        for table in inspector.get_table_names():
            if table == 'alembic_version':
                continue
            keys = inspector.get_pk_constraint(table)['constrained_columns']
            columns = ','.join(quote(c['name']) for c in inspector.get_columns(table))
            ordering = ','.join(quote(key) for key in keys)
            statement = db.text('SELECT ' + columns + ' FROM ' + quote(table) + (' ORDER BY ' + ordering if ordering else ''))
            snapshots[table] = statement, db.session.execute(statement).all()
        db.session.remove()
        parent = Path(app.root_path).parent / '.runtime/backups' / ('antes_actualizacion13_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        backup(parent)
        upgrade(revision='0013_notas_compensatorias')
        for table, (statement, previous) in snapshots.items():
            if db.session.execute(statement).all() != previous:
                raise RuntimeError('La verificación posterior no coincide para ' + table + '. Conserva el respaldo y revisa la base.')
        if db.session.scalar(db.text('SELECT version_num FROM alembic_version')) != '0013_notas_compensatorias':
            raise RuntimeError('La revisión final no coincide.')
        print('Migración 13 verificada: todas las filas, cuentas, permisos, históricos, documentos y auditorías conservados.')
        print('Se añadió la tabla privada de notas emitidas y sus protecciones.')


if __name__ == '__main__':
    main()
