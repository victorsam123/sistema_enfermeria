# Archivos de la actualización 7

Fuentes completas en `fuentes_actualizacion7.zip`. Comparación con la entrega anterior.

## Nuevos

- `ACTUALIZACION_7.md`
- `app/hospital_services/__init__.py`
- `app/hospital_services/catalog.py`
- `app/hospital_services/classification.py`
- `app/hospital_services/excel.py`
- `app/hospital_services/folders.py`
- `app/hospital_services/forms.py`
- `app/hospital_services/records.py`
- `app/hospital_services/report_data.py`
- `app/hospital_services/reports.py`
- `app/hospital_services/settings.py`
- `app/models/hospital_services.py`
- `app/static/css/hospital_services.css`
- `app/static/js/service_selection.js`
- `app/templates/hospital_services/folder.html`
- `app/templates/hospital_services/folders.html`
- `app/templates/hospital_services/history.html`
- `app/templates/hospital_services/macros.html`
- `app/templates/hospital_services/reclassify.html`
- `app/templates/hospital_services/records.html`
- `app/templates/hospital_services/reports.html`
- `app/templates/hospital_services/service_dialog.html`
- `app/templates/hospital_services/service_selector.html`
- `app/templates/hospital_services/settings.html`
- `migrations/versions/0006_servicios_e_informes.py`
- `scripts/migrar_actualizacion7.py`
- `tests/service-selection-ui.test.cjs`
- `tests/test_service_files_reports.py`

## Modificados

- `app/administration/__init__.py`
- `app/administration/forms.py`
- `app/administration/guardia_records.py`
- `app/administration/guardias.py`
- `app/administration/justificativos.py`
- `app/administration/leave_records.py`
- `app/administration/reposos/views.py`
- `app/dashboard_modules.py`
- `app/models/administration.py`
- `app/models/leave_records.py`
- `app/models/reposos.py`
- `app/static/css/app.css`
- `app/templates/administration/base.html`
- `app/templates/administration/comisionados.html`
- `app/templates/administration/guardias.html`
- `app/templates/administration/justificativos.html`
- `app/templates/administration/leave_macros.html`
- `app/templates/administration/reposo.html`
- `app/templates/administration/vacaciones.html`
- `app/templates/dashboard.html`
- `app/templates/includes/sidebar.html`
- `README.md`
- `requirements.lock.txt`
- `requirements.txt`
- `scripts/initialize.py`
- `tests/test_administration.py`
- `tests/test_guardias_multifecha.py`
- `tests/test_leave_records.py`
- `tests/test_reposos.py`
- `VALIDACION.md`

## Conservados

Se comprobó la conservación byte por byte de la factoría general, modelo y protección de usuarios, autenticación, rutas principales, configuración, encabezado y entrada WSGI. Las migraciones anteriores se conservan. No se eliminó ningún archivo anterior.

El paquete no incluye .env, credenciales PostgreSQL, .runtime, respaldos, la referencia Excel ni registros de prueba.
