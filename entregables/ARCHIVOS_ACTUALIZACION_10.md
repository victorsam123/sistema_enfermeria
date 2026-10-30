# Archivos de la actualización 10

Comparación con la entrega 9. No se eliminan archivos anteriores. Login, usuarios, configuración y protecciones se conservan.

## Archivos nuevos

- `ACTUALIZACION_10.md`
- `app/employees/__init__.py`
- `app/employees/forms.py`
- `app/employees/lookup.py`
- `app/employees/rules.py`
- `app/employees/services.py`
- `app/employees/views.py`
- `app/models/employees.py`
- `app/static/css/employees.css`
- `app/static/js/employees.js`
- `app/templates/employees/base.html`
- `app/templates/employees/detail.html`
- `app/templates/employees/form.html`
- `app/templates/employees/history.html`
- `app/templates/employees/lookup.html`
- `app/templates/employees/photo.html`
- `app/templates/employees/photo_upload.html`
- `app/templates/employees/search.html`
- `migrations/versions/0009_funcionarios.py`
- `scripts/migrar_actualizacion10.py`
- `tests/employees.test.cjs`
- `tests/test_employees.py`

## Archivos modificados

- `README.md`
- `VALIDACION.md`
- `app/__init__.py`
- `app/administration/forms.py`
- `app/administration/guardias.py`
- `app/administration/justificativos.py`
- `app/administration/leave_records.py`
- `app/administration/reposos/views.py`
- `app/dashboard_modules.py`
- `app/documents/__init__.py`
- `app/documents/service.py`
- `app/models/administration.py`
- `app/models/documents.py`
- `app/models/leave_records.py`
- `app/models/reposos.py`
- `app/security/permissions.py`
- `app/templates/administration/base.html`
- `app/templates/administration/comisionados.html`
- `app/templates/administration/guardias.html`
- `app/templates/administration/justificativos.html`
- `app/templates/administration/reposo.html`
- `app/templates/administration/vacaciones.html`
- `app/templates/includes/sidebar.html`
- `requirements.txt`
- `scripts/initialize.py`

## Entrega y validación

- Paquete completo: `fuentes_actualizacion10.zip`.
- Migración: `0009_funcionarios`. Respaldo conjunto: `scripts/migrar_actualizacion10.py`.
- 323 pruebas Python y 33 JavaScript aprobadas, incluidas 56 pruebas de funcionarios.
- Guía: `ACTUALIZACION_10.md`. Resultados: `VALIDACION.md`.
- Excluye secretos, datos PostgreSQL, fotografías, instance/ y respaldos privados.
- La vinculación por cédula es explícita; no se asocian registros antiguos por nombres.
- Se reutiliza el almacenamiento privado local/S3 existente. No se contrató ni configuró un bucket nuevo.
