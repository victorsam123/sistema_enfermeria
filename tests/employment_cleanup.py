"""Limpieza privilegiada EXCLUSIVAMENTE en PostgreSQL de pruebas."""
from sqlalchemy.engine import make_url
from app.extensions import db


def clear_employment_test_rows():
    if not make_url(str(db.engine.url)).database.endswith('_test'):
        raise RuntimeError('La limpieza de vínculos solo está permitida en una base _test.')
    db.session.execute(db.text('DELETE FROM documentos_vinculos_laborales'))
    # La protección de borrado se deshabilita solo dentro de esta transacción
    # de la base de pruebas; la aplicación no utiliza este procedimiento.
    db.session.execute(db.text('ALTER TABLE vinculos_laborales DISABLE TRIGGER vinculo_no_delete'))
    db.session.execute(db.text('DELETE FROM vinculos_laborales'))
    db.session.execute(db.text('ALTER TABLE vinculos_laborales ENABLE TRIGGER vinculo_no_delete'))
