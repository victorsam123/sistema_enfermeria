# Archivos de la actualización 8

Inventario comparado con la entrega 7. Se conservan login, servicios y registros existentes.

## Nuevos

- `ACTUALIZACION_8.md`
- `app/administration/record_access.py`
- `app/administration/record_lifecycle.py`
- `app/administration/record_print.py`
- `app/models/user_audit.py`
- `app/security/__init__.py`
- `app/security/first_access.py`
- `app/security/passwords.py`
- `app/security/permissions.py`
- `app/security/user_forms.py`
- `app/security/user_operations.py`
- `app/security/users.py`
- `app/static/css/user_accounts.css`
- `app/static/js/print_record.js`
- `app/static/js/user_accounts.js`
- `app/templates/administration/delete_record.html`
- `app/templates/administration/deleted_record.html`
- `app/templates/administration/print_record.html`
- `app/templates/administration/trash.html`
- `app/templates/users/activity.html`
- `app/templates/users/base.html`
- `app/templates/users/form.html`
- `app/templates/users/index.html`
- `app/templates/users/macros.html`
- `app/templates/users/password.html`
- `app/templates/users/reset_password.html`
- `app/templates/users/state.html`
- `migrations/versions/0007_usuarios_roles_y_eliminacion.py`
- `scripts/migrar_actualizacion8.py`
- `tests/legacy_migration_helpers.py`
- `tests/test_users_rbac.py`
- `tests/user-accounts-ui.test.cjs`

## Modificados

- `README.md`
- `app/__init__.py`
- `app/administration/__init__.py`
- `app/administration/comisionados.py`
- `app/administration/guardia_records.py`
- `app/administration/guardias.py`
- `app/administration/justificativos.py`
- `app/administration/leave_records.py`
- `app/administration/reposo.py`
- `app/administration/reposos/views.py`
- `app/administration/services.py`
- `app/administration/vacaciones.py`
- `app/dashboard_modules.py`
- `app/hospital_services/classification.py`
- `app/hospital_services/folders.py`
- `app/hospital_services/records.py`
- `app/hospital_services/reports.py`
- `app/hospital_services/settings.py`
- `app/models/__init__.py`
- `app/models/administration.py`
- `app/models/hospital_services.py`
- `app/models/leave_records.py`
- `app/models/reposos.py`
- `app/routes/auth.py`
- `app/routes/main.py`
- `app/services.py`
- `app/templates/administration/base.html`
- `app/templates/administration/comisionados.html`
- `app/templates/administration/guardias.html`
- `app/templates/administration/justificativos.html`
- `app/templates/administration/reposo.html`
- `app/templates/administration/vacaciones.html`
- `app/templates/base.html`
- `app/templates/dashboard.html`
- `app/templates/hospital_services/folders.html`
- `app/templates/hospital_services/history.html`
- `app/templates/hospital_services/macros.html`
- `app/templates/includes/header.html`
- `app/templates/includes/sidebar.html`
- `scripts/initialize.py`
- `scripts/migrar_actualizacion7.py`
- `tests/test_administration.py`
- `tests/test_auth.py`
- `tests/test_dashboard_clock.py`
- `tests/test_guardias_multifecha.py`
- `tests/test_leave_records.py`
- `tests/test_reposos.py`
- `tests/test_service_files_reports.py`

Validación previa a adjuntos: 219 pruebas Python y 28 JavaScript aprobadas. Ver ACTUALIZACION_8.md.
