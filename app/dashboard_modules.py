"""Accesos del Dashboard. Cada módulo futuro registrará su propio Blueprint.

Al habilitarlo, asignar endpoint='nombre_blueprint.vista' después de registrar
el Blueprint en create_app. Mientras endpoint sea None solo se muestra el aviso.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardModule:
    slug: str
    label: str
    icon: str
    endpoint: str | None = None
    permission: str = 'records.create'


DASHBOARD_MODULES = (
    DashboardModule('justificativo', 'Justificativo', 'bi-file-earmark-medical', 'justificativos.index'),
    DashboardModule('reposo', 'Reposo', 'bi-heart-pulse', 'reposo.index'),
    DashboardModule('cambio-guardia', 'Cambio de Guardia', 'bi-arrow-left-right', 'guardias.opciones'),
    DashboardModule('vacaciones', 'Vacaciones', 'bi-calendar2-week', 'vacaciones.index'),
    DashboardModule('comisionados', 'Comisionados', 'bi-people', 'comisionados.index'),
    DashboardModule('archivos-servicio', 'Archivos por Servicio', 'bi-folder2-open', 'service_files.index', 'files.read'),
    DashboardModule('informes', 'Informes Excel', 'bi-file-earmark-spreadsheet', 'reports.index', 'reports.export'),
    DashboardModule('usuarios', 'Gestión de Usuarios', 'bi-person-gear', 'users.index', 'users.manage'),
    DashboardModule('funcionario', 'Funcionario', 'bi-person-vcard', 'employees.search', 'employees.read'),
)
