"""Registro modular de los Blueprints administrativos."""
from app.dashboard_clock import PARAGUAY_TIMEZONE, clock_snapshot
from flask import request


def register_administration(app):
    # Importar los modelos permite a Alembic detectar sus metadatos.
    from app.models.administration import Justificativo, CambioGuardia
    from app.models.leave_records import Comisionado, Vacacion
    from app.models.issued_notes import NotaCompensatoria
    from app.administration.justificativos import bp as justificativos_bp
    from app.administration.reposo import bp as reposo_bp
    from app.administration.guardias import bp as guardias_bp
    from app.administration.comisionados import bp as comisionados_bp
    from app.administration.vacaciones import bp as vacaciones_bp
    from app.hospital_services.folders import bp as folders_bp
    from app.hospital_services.settings import bp as settings_bp
    from app.hospital_services.reports import bp as reports_bp
    from app.security.users import bp as users_bp
    from app.administration.record_lifecycle import bp as lifecycle_bp
    from app.administration.record_print import bp as print_bp
    from app.administration.compensatory_notes import bp as notes_bp
    blueprints = (justificativos_bp, reposo_bp, guardias_bp, comisionados_bp, vacaciones_bp,
                  folders_bp, settings_bp, reports_bp, users_bp, lifecycle_bp, print_bp, notes_bp)
    for blueprint in blueprints:
        app.register_blueprint(blueprint)

    @app.context_processor
    def administrative_clock():
        if request.blueprint in {blueprint.name for blueprint in blueprints}:
            return {'clock': clock_snapshot()}
        return {}

    @app.template_filter('fecha_local')
    def fecha_local(value):
        return value.astimezone(PARAGUAY_TIMEZONE).strftime('%d/%m/%Y %H:%M:%S') if value else '—'
