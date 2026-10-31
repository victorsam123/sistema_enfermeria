"""Una única definición de módulos y fechas para carpetas, vista previa y Excel."""
from dataclasses import dataclass
from app.extensions import db
from app.models.administration import Justificativo, CambioGuardia, DetalleCambioGuardia
from app.models.reposos import Reposo
from app.models.leave_records import Vacacion, Comisionado


@dataclass(frozen=True)
class Category:
    label: str
    model: type
    start: str
    end: str | None
    fields: tuple
    edit_endpoint: str
    kind: str | None = None


CATEGORIES = {
    'justificativos': Category('Justificativos', Justificativo, 'fecha_inasistencia', None,
        (('nombres_apellidos', 'Nombres y Apellidos'), ('fecha_inasistencia', 'Fecha de inasistencia'),
         ('motivo', 'Motivo'), ('fecha_cobertura', 'Fecha de cobertura')), 'justificativos.edit'),
    'reposos': Category('Reposos', Reposo, 'fecha_desde', 'fecha_hasta',
        (('nombres_apellidos', 'Nombre y Apellido'), ('fecha_desde', 'Fecha desde'), ('fecha_hasta', 'Fecha hasta'),
         ('total_dias', 'Total de días'), ('diagnostico', 'Diagnóstico'),
         ('fecha_entrega_departamento', 'Fecha de entrega al Dpto.')), 'reposo.edit'),
    'guardias': Category('Cambios de Guardia', CambioGuardia, 'fecha_cambio', None, (), 'guardias.normal_edit', 'NORMAL'),
    'pagadas': Category('Cambios de Guardia Pagada', CambioGuardia, 'fecha_cambio', None, (), 'guardias.pagada_edit', 'PAGADA'),
    'reemplazos': Category('Cambios con Reemplazante', CambioGuardia, 'fecha_cambio', None, (), 'guardias.reemplazante_edit', 'REEMPLAZO'),
    'emergencias': Category('Cambios de Emergencia', CambioGuardia, 'fecha_cambio', None, (), 'guardias.emergencia_edit', 'EMERGENCIA'),
    'vacaciones': Category('Vacaciones', Vacacion, 'fecha_inicio', 'fecha_termino',
        (('nombres_apellidos', 'Nombres y Apellidos'), ('fecha_inicio', 'Inicio'), ('fecha_termino', 'Término'),
         ('total_dias', 'Total de días')), 'vacaciones.edit'),
    'comisionados': Category('Comisionados', Comisionado, 'fecha_inasistencia', None,
        (('nombres_apellidos', 'Nombres y Apellidos'), ('fecha_inasistencia', 'Fecha de inasistencia'),
         ('motivo', 'Motivo'), ('lugar', 'Lugar')), 'comisionados.edit'),
}
MODELS = (Justificativo, Reposo, CambioGuardia, Vacacion, Comisionado)


def record_query(category, service_id, start=None, end=None, search=None):
    model = category.model
    query = db.select(model).where(model.servicio_id == service_id, model.eliminado.is_(False))
    if category.kind:
        query = query.where(model.tipo_cambio == category.kind)
        dates = []
        if start:
            dates.append(DetalleCambioGuardia.fecha_guardia >= start)
        if end:
            dates.append(DetalleCambioGuardia.fecha_guardia <= end)
        if dates:
            query = query.where(model.detalles.any(db.and_(*dates)))
        if search:
            query = query.where(db.or_(model.solicitante.icontains(search, autoescape=True),
                model.reemplazante.icontains(search, autoescape=True)))
        latest = db.select(db.func.min(DetalleCambioGuardia.fecha_guardia)).where(
            DetalleCambioGuardia.cambio_guardia_id == model.id).correlate(model).scalar_subquery()
        return query.order_by(latest.asc(), model.id.asc())
    if search:
        query = query.where(model.nombres_apellidos.icontains(search, autoescape=True))
    if start:
        query = query.where(getattr(model, category.end or category.start) >= start)
    if end:
        query = query.where(getattr(model, category.start) <= end)
    return query.order_by(getattr(model, category.start).asc(), model.id.asc())


def matching_details(record, start=None, end=None):
    return [d for d in record.detalles if (not start or d.fecha_guardia >= start) and (not end or d.fecha_guardia <= end)]


def folder_statistics():
    rows = db.union_all(*(db.select(m.servicio_id.label('servicio_id'), m.fecha_creacion.label('fecha')).where(m.eliminado.is_(False)) for m in MODELS)).subquery()
    return db.select(rows.c.servicio_id, db.func.count().label('total'), db.func.max(rows.c.fecha).label('ultima')).group_by(rows.c.servicio_id).subquery()
