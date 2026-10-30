"""Solo semillas en esquemas históricos aislados de la base _test."""
from uuid import uuid4
from werkzeug.security import generate_password_hash
from app.extensions import db


def legacy_admin():
    # El modelo actual no se consulta contra columnas todavía inexistentes.
    db.session.execute(db.text("""INSERT INTO usuarios(nombre,username,password_hash,rol,activo,protegido)
        VALUES ('Victor','victor',:hash,'Superadministrador',true,true)
        ON CONFLICT(username) DO NOTHING"""), {'hash': generate_password_hash('513625', method='scrypt')})
    db.session.commit()
    return db.session.execute(db.text("SELECT id FROM usuarios WHERE username='victor'")).scalar_one()
