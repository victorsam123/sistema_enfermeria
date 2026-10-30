# Archivos de la actualización 9

Comparación con la entrega 8. No se eliminan archivos anteriores. PostgreSQL conserva las cuentas, servicios, registros e historiales.

## Archivos nuevos

- `ACTUALIZACION_9.md`
- `app/documents/__init__.py`
- `app/documents/images.py`
- `app/documents/maintenance.py`
- `app/documents/service.py`
- `app/documents/storage.py`
- `app/documents/views.py`
- `app/models/documents.py`
- `app/static/css/documents.css`
- `app/static/js/documents.js`
- `app/templates/documents/gallery.html`
- `app/templates/documents/macros.html`
- `app/templates/documents/retire.html`
- `app/templates/documents/upload.html`
- `migrations/versions/0008_documentos_adjuntos.py`
- `scripts/migrar_actualizacion9.py`
- `scripts/respaldar_documentos.py`
- `tests/documents.test.cjs`
- `tests/test_documents.py`

## Archivos modificados

- `.env.example`
- `README.md`
- `VALIDACION.md`
- `app/__init__.py`
- `app/administration/forms.py`
- `app/administration/guardia_records.py`
- `app/administration/guardias.py`
- `app/administration/justificativos.py`
- `app/administration/leave_records.py`
- `app/administration/reposos/views.py`
- `app/administration/services.py`
- `app/hospital_services/excel.py`
- `app/models/hospital_services.py`
- `app/security/permissions.py`
- `app/templates/administration/base.html`
- `app/templates/administration/comisionados.html`
- `app/templates/administration/guardias.html`
- `app/templates/administration/justificativos.html`
- `app/templates/administration/reposo.html`
- `app/templates/administration/vacaciones.html`
- `app/templates/hospital_services/macros.html`
- `config.py`
- `requirements.lock.txt`
- `requirements.txt`
- `scripts/initialize.py`

## Entrega y validación

- Paquete completo: `fuentes_actualizacion9.zip`.
- Migración: `0008_documentos_adjuntos`, con respaldo mediante `scripts/migrar_actualizacion9.py`.
- 267 pruebas Python y 31 JavaScript aprobadas; consulta `VALIDACION.md`.
- Almacenamiento privado local listo. S3 integrado y probado con Stubber, pendiente de bucket y credenciales del proveedor.
- Configuración, pruebas, respaldo y despliegue: `ACTUALIZACION_9.md`.
- Excluye .env, instance/, .runtime/, originales sensibles, datos PostgreSQL y respaldos.
