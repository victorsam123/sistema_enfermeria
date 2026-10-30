# Archivos de la actualización 11

Comparación con fuentes_actualizacion10.zip. No se eliminan archivos anteriores. 189 archivos anteriores conservados byte por byte. Login, contraseñas, protección de victor, configuración, Dashboard y módulos administrativos anteriores permanecen intactos.

## Archivos nuevos

- `ACTUALIZACION_11.md`
- `app/employees/employment_forms.py`
- `app/employees/employment_services.py`
- `app/employees/employment_views.py`
- `app/employees/expedient.py`
- `app/models/employment_links.py`
- `app/static/css/employment_links.css`
- `app/static/js/employment_links.js`
- `app/templates/employees/employment_form.html`
- `app/templates/employees/employment_history_details.html`
- `app/templates/employees/employment_section.html`
- `app/templates/employees/employment_state.html`
- `app/templates/employees/expedient.html`
- `app/templates/employees/institutional_data.html`
- `app/templates/employees/institutional_form.html`
- `migrations/versions/0010_vinculos_laborales.py`
- `scripts/migrar_actualizacion11.py`
- `tests/employment-links.test.cjs`
- `tests/employment_cleanup.py`
- `tests/test_employment_links.py`

## Archivos modificados

- `README.md`
- `VALIDACION.md`
- `app/employees/__init__.py`
- `app/employees/forms.py`
- `app/employees/services.py`
- `app/employees/views.py`
- `app/models/employees.py`
- `app/security/permissions.py`
- `app/templates/employees/base.html`
- `app/templates/employees/detail.html`
- `app/templates/employees/form.html`
- `app/templates/employees/history.html`
- `scripts/initialize.py`
- `tests/test_employees.py`

## Entrega y validación

- Paquete completo: `fuentes_actualizacion11.zip`.
- Migración: `0010_vinculos_laborales`; respaldo/verificación: `scripts/migrar_actualizacion11.py`.
- Nuevas tablas: `vinculos_laborales` y `documentos_vinculos_laborales` (referencias futuras, sin copiar archivos).
- Una ficha por cédula, fechas independientes, conteo activo calculado, edición, desactivación/reactivación y auditoría.
- 348 pruebas Python y 36 JavaScript aprobadas. Comprobaciones de migración, concurrencia, permisos, persistencia y HTTP real.
- Guía: `ACTUALIZACION_11.md`; resultados comprobados: `VALIDACION.md`.
- Respaldo privado previo: `.runtime/backups/antes_actualizacion11_20261022_221840_459343/`.
- Excluye secretos, .env de uso, PostgreSQL, .runtime, instance/, fotografías y respaldos privados.
- El contador manual anterior se archiva; no se inventan vínculos adicionales ni fechas.
- Se reutiliza el almacenamiento privado existente y no se configura un proveedor externo nuevo.
