"""Respalda y amplía categorías sin reescribir registros. Servidor detenido."""
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
        if revision == '0012_guardias_intercambio':
            print('Actualización 12 ya aplicada. No se modificaron los datos.')
            return
        if revision != '0011_carrera_funcionarios':
            raise RuntimeError('Se requiere la revisión 0011_carrera_funcionarios. Aplica primero las actualizaciones anteriores con su respaldo.')
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
        parent = Path(app.root_path).parent / '.runtime/backups' / ('antes_actualizacion12_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        backup(parent)
        upgrade(revision='0012_guardias_intercambio')
        for table, (statement, previous) in snapshots.items():
            if db.session.execute(statement).all() != previous:
                raise RuntimeError('La verificación posterior no coincide para ' + table + '. Conserva el respaldo y revisa la base.')
        if db.session.scalar(db.text('SELECT version_num FROM alembic_version')) != '0012_guardias_intercambio':
            raise RuntimeError('La revisión final no coincide.')
        print('Migración 12 verificada: todas las filas, cuentas, permisos, históricos, documentos y auditorías conservados.')
        print('Solo se ampliaron restricciones de categorías y su asociación documental.')


if __name__ == '__main__':
    main()
