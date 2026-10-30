from uuid import UUID
from sqlalchemy.orm.exc import StaleDataError
from app.extensions import db
from app.models.employees import Funcionario
from app.models.employment_links import VinculoLaboral
from app.employees.rules import paraguay_today


class EmploymentConflict(ValueError):
    pass


def validate_entry(record, entry):
    if entry is None or entry > paraguay_today() or entry < record.fecha_nacimiento:
        raise EmploymentConflict('La fecha debe ser completa, no futura y no anterior al nacimiento del funcionario.')


def next_number(record_id):
    return (db.session.scalar(db.select(db.func.max(VinculoLaboral.numero_vinculo)).where(
        VinculoLaboral.funcionario_id == record_id)) or 0) + 1


def parent_locked(record_id):
    return db.session.scalar(db.select(Funcionario).where(Funcionario.id == record_id)
        .with_for_update(of=Funcionario).execution_options(populate_existing=True))


def add_link(record_id, entry, user_id, request_id, expected_version=None):
    parent = parent_locked(record_id)
    if parent is None:
        raise EmploymentConflict('La ficha no existe.')
    previous = db.session.scalar(db.select(VinculoLaboral).where(VinculoLaboral.solicitud_id == UUID(str(request_id))))
    if previous:
        if previous.funcionario_id != record_id or previous.fecha_ingreso != entry or previous.usuario_registro_id != user_id:
            raise EmploymentConflict('Este formulario ya fue utilizado con otros datos. Recarga la ficha.')
        return previous
    if expected_version is not None and str(parent.version) != str(expected_version):
        raise StaleDataError()
    validate_entry(parent, entry)
    row = VinculoLaboral(funcionario_id=record_id, numero_vinculo=next_number(record_id), fecha_ingreso=entry,
        activo=True, usuario_registro_id=user_id, solicitud_id=UUID(str(request_id)))
    db.session.add(row)
    db.session.flush()  # PostgreSQL numera/valida, audita y actualiza el total.
    db.session.refresh(parent)
    return row


def locked_link(record_id, link_id, version):
    parent = parent_locked(record_id)
    row = db.session.scalar(db.select(VinculoLaboral).where(VinculoLaboral.id == link_id,
        VinculoLaboral.funcionario_id == record_id).with_for_update(of=VinculoLaboral).execution_options(populate_existing=True))
    if not row or str(row.version) != str(version):
        raise StaleDataError()
    return parent, row


def update_link(record_id, link_id, entry, version, user_id):
    parent, row = locked_link(record_id, link_id, version)
    validate_entry(parent, entry)
    if row.fecha_ingreso != entry:
        row.fecha_ingreso, row.usuario_modificacion_id = entry, user_id
        db.session.flush()
        db.session.refresh(parent)
    return row


def change_state(record_id, link_id, active, reason, version, user_id):
    parent, row = locked_link(record_id, link_id, version)
    if row.activo == active:
        raise EmploymentConflict('El vínculo ya tiene ese estado. Recarga la ficha.')
    row.activo, row.usuario_modificacion_id, row.motivo_estado = active, user_id, reason
    db.session.flush()
    db.session.refresh(parent)
    return row
