from flask import request
from app.dashboard_clock import clock_snapshot


def configure_employees(app):
    from app.models.employees import Funcionario
    from app.models.employment_links import VinculoLaboral, DocumentoVinculoLaboral
    from app.employees.views import bp
    from app.employees.lookup import lookup_ticket
    from app.employees.expedient import register_expedient
    # Registrar una sola vez, incluso al crear varias aplicaciones de pruebas.
    if not getattr(bp, '_expedient_registered', False):
        register_expedient(bp)
        bp._expedient_registered = True
    app.register_blueprint(bp)
    from app.employees.employment_views import bp as employment_bp
    app.register_blueprint(employment_bp)
    app.jinja_env.globals['employee_lookup_ticket'] = lookup_ticket

    @app.context_processor
    def employee_clock():
        return {'clock': clock_snapshot()} if request.blueprint in {'employees', 'employment_links'} else {}
