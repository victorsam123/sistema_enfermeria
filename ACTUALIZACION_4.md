# Actualización 4 · Comisionados y Vacaciones

La ampliación está aplicada en esta computadora y se sirve en **http://127.0.0.1:5000**. Se conservan el login, las sesiones, `.env`, el Dashboard con sus cinco accesos, el reloj Paraguay, Justificativos, ambos cambios de guardia y la protección de `victor`.

## Reposo: pendiente de la foto 3

Reposo conserva sus accesos a Cambio de Guardia y Cambio de Guardia Pagada. Se reservó el paquete `app/administration/reposos/` para el futuro registro de reposos. No define campos, modelos, rutas ni migraciones. La foto 3 deberá establecer primero los datos del formulario; no se inventaron campos ni se modificó la tabla de cambios de guardia.

## Funciones incorporadas

**Comisionados** permite registrar nombres y apellidos, fecha de inasistencia, motivo y lugar. Incluye listado paginado, búsqueda por nombre, filtro inclusivo de fecha de inasistencia, orden de fechas ascendente o descendente y edición autorizada. El orden inicial muestra las fechas más recientes primero.

**Vacaciones** permite registrar nombres y apellidos, inicio y término. El total de días es de solo lectura, se actualiza al cambiar las fechas y se vuelve a calcular en Python al guardar y editar. Se incluyen todos los días calendario: ambos extremos, sábados, domingos y feriados. El mismo día cuenta como uno. Se rechaza un término anterior al inicio.

La regla Python está aislada en `app/administration/vacation_rules.py`. PostgreSQL también verifica que el total coincida con las fechas. Para una futura regla institucional diferente deberán actualizarse conjuntamente esta función, el cálculo de presentación en `vacaciones.js` y la restricción de PostgreSQL mediante una nueva migración.

En Vacaciones, los filtros muestran los períodos que se superponen total o parcialmente con el rango indicado. Por ejemplo, unas vacaciones del 01/11 al 15/11 aparecen al buscar el día 10/11. El orden inicial es cronológico por inicio; puede invertirse desde el selector de orden.

### Planilla de vacaciones 2026/2027

La opción **IMPRIMIR PLANILLA** presenta el formato de la planilla recibida y abre la impresión del navegador. **DESCARGAR EXCEL** genera un libro basado directamente en `app/assets/planilla_vacaciones_2026_2027.xlsx`, conservando las celdas combinadas, estilos, configuración de página y diseño original. Ambas opciones requieren indicar las fechas **Desde** y **Hasta**; incluyen los períodos de vacaciones que se superponen con ese rango. La observación queda en blanco para completarse manualmente.

La planilla toma cédula, carrera y vínculos de la ficha seleccionada. Un funcionario con varios vínculos activos ocupa una fila: el ingreso y la antigüedad corresponden al vínculo activo más antiguo y la columna **VINCULO** enumera todos los números de vínculo activos. Las fichas existentes conservan la carrera vacía hasta que se complete manualmente. El rubro es **111** para `LIC. EN ENFERMERIA` y **142** para `TEC. EN ENFERMERIA`; `AUX. EN ENFERMERA` y `CAMILLERO` quedan sin rubro hasta que se indiquen sus códigos. Para nuevas vacaciones, seleccionar una ficha de funcionario es obligatorio. Los registros históricos sin ficha se conservan; las columnas de identidad no disponibles quedan vacías y se notifican en la vista previa.

La migración `0011_carrera_funcionarios` agrega la carrera como campo opcional en PostgreSQL para preservar fichas ya existentes. El formulario requiere elegirla al crear o editar una ficha. No modifica los registros de vacaciones ni inventa carreras.

Los dos módulos registran creador y hora de carga. La edición conserva ambos e identifica al último editor y la hora de modificación. Solo el rol Superadministrador puede acceder y editar actualmente. Las páginas incluyen navegación institucional, reloj, usuario y cierre de sesión.

## Actualizar otra instalación existente en Windows

En esta computadora estos pasos ya se realizaron. Para actualizar otra instalación:

1. Conserva `.env` y la base PostgreSQL existente. Haz un respaldo con pgAdmin o `pg_dump` y una copia de los archivos actuales. No reemplaces `.runtime/pgdata` ni copies una base de otra computadora.
2. Detén únicamente el proceso Flask/Waitress con Ctrl+C en su terminal, copia los archivos actualizados y conserva la configuración local. Esta ampliación no cambia las dependencias.
3. Desde la carpeta del proyecto ejecuta:

```powershell
.venv/Scripts/python.exe -m flask --app run db upgrade
.venv/Scripts/python.exe -m flask --app run db check
.venv/Scripts/python.exe -m waitress --listen=127.0.0.1:5000 run:app
```

Para el Python portátil de esta computadora:

```powershell
.runtime/python/python.exe -s -m flask --app run db upgrade
.runtime/python/python.exe -s -m flask --app run db check
.runtime/python/python.exe -s -m waitress --listen=127.0.0.1:5000 run:app
```

4. Abre el sistema y recarga el Dashboard. Vacaciones y Comisionados ahora enlazan a sus propias secciones. Las otras tres tarjetas mantienen sus destinos.

La migración `0003_comisionados_vacaciones` sucede a `0002_administrative_records`. Añade únicamente las dos tablas nuevas, índices y restricciones. No inicializa cuentas, restablece contraseñas ni altera tablas previas. Volver a ejecutar `db upgrade` no duplica tablas ni registros. El downgrade destructivo está bloqueado.

En producción, ejecuta las migraciones con el propietario del esquema. A la cuenta de ejecución concede SELECT/INSERT/UPDATE sobre `comisionados` y `vacaciones` y USAGE/SELECT sobre sus secuencias, conservando sus permisos anteriores. No hacen falta privilegios de eliminación ni modificación del esquema.

## Pruebas manuales

### Comisionados

1. Inicia sesión con la contraseña vigente del administrador y abre **Comisionados**.
2. Completa nombres, fecha en `DD/MM/AAAA`, motivo y lugar. Los selectores permiten usar el calendario o escribir la fecha. El nombre admite 3–180 caracteres, el motivo 3–2000 y el lugar 2–250.
3. Pulsa **GUARDAR COMISIONADO**. Debe aparecer «Comisionado registrado correctamente», el registro en la tabla y un formulario limpio.
4. Usa **VER REGISTROS**, busca una parte del nombre, filtra un rango de fechas y cambia el orden. Para consultar una fecha exacta, coloca el mismo día en Desde y Hasta.
5. Pulsa **Editar**, cambia el lugar o el motivo y guarda. Deben conservarse el creador y la fecha de carga, y mostrarse los datos de modificación.
6. **CANCELAR** vuelve al Dashboard durante una carga nueva o al listado durante una edición, sin guardar los cambios del formulario.

### Vacaciones

1. Abre **Vacaciones**, ingresa el nombre y selecciona inicio `01/11/2026` y término `15/11/2026`. El total debe ser **15** y no permitir edición manual.
2. Cambia el término a `20/11/2026`: debe mostrar **20**. Si eliges el mismo día para ambas fechas, debe mostrar **1**.
3. Prueba un término anterior al inicio: debe impedirse guardar y no mostrarse un total negativo. Una fecha inexistente también debe rechazarse.
4. Pulsa **GUARDAR VACACIONES**. Debe aparecer «Vacaciones registradas correctamente» y la fila con las fechas y el total calculado.
5. Busca el nombre y filtra por un día incluido dentro del período: el registro debe aparecer aunque sus vacaciones hayan comenzado antes de Desde.
6. Edita el período y guarda. El total debe recalcularse tanto en pantalla como en PostgreSQL. Un valor `total_dias` adulterado en el envío se ignora: no participa de los datos autorizados del formulario.
7. Vincula las vacaciones a una ficha mediante la búsqueda por cédula. La carga sin ficha debe rechazarse.
8. En la lista de vacaciones filtra `01/11/2026` a `31/10/2027`, selecciona **IMPRIMIR PLANILLA** y comprueba las columnas y los códigos 111/142. Usa **DESCARGAR EXCEL** para verificar el mismo contenido y el formato de la plantilla original. Auxiliar y Camillero no deben recibir un rubro inventado; la observación debe quedar vacía.

### Persistencia y continuidad

- Cierra sesión y vuelve a entrar: los registros deben conservarse. Reiniciar únicamente la aplicación también debe conservarlos.
- Comprueba Justificativo, Reposo, Cambio de Guardia y Cambio de Guardia Pagada, junto con el reloj y los cinco accesos del Dashboard.
- Abre una URL de estos módulos en una ventana privada: debe pedir iniciar sesión. Un usuario sin rol Superadministrador no puede acceder ni editar.
- Campos vacíos, fechas inexistentes y formularios sin CSRF deben rechazarse. No hay rutas de eliminación en los nuevos módulos.
- Un doble envío del mismo formulario se identifica mediante una clave UUID única en PostgreSQL. No duplica la carga; un formulario nuevo permite un registro legítimo con datos iguales.
- Abre una edición en dos pestañas: tras guardar una, el envío de la otra debe pedir recargar para revisar el registro, sin sobrescribir la versión actual.
- Las tablas muestran hasta 20 registros por página. Los filtros y el orden se conservan al paginar.

## Archivos nuevos y modificados

Nuevos:

```text
app/models/leave_records.py
app/administration/leave_forms.py
app/administration/leave_records.py
app/administration/comisionados.py
app/administration/vacaciones.py
app/administration/vacation_roster.py
app/employees/careers.py
app/administration/vacation_rules.py
app/administration/reposos/__init__.py
app/templates/administration/leave_base.html
app/templates/administration/leave_macros.html
app/templates/administration/comisionados.html
app/templates/administration/vacaciones.html
app/templates/administration/vacation_roster.html
app/assets/planilla_vacaciones_2026_2027.xlsx
app/static/images/vacation_roster_logo.jpeg
app/static/css/leave_records.css
app/static/css/vacation_roster.css
app/static/js/vacaciones.js
migrations/versions/0003_comisionados_vacaciones.py
migrations/versions/0011_carrera_funcionarios.py
tests/test_leave_records.py
tests/vacaciones-ui.test.cjs
ACTUALIZACION_4.md
```

Modificados:

```text
app/administration/__init__.py     Registra los nuevos Blueprints y sus relojes
app/dashboard_modules.py          Vincula las dos tarjetas a sus módulos
app/templates/includes/sidebar.html Añade navegación a ambos módulos
tests/test_auth.py                Comprueba los cinco accesos habilitados
README.md
VALIDACION.md
```

El código del login, la configuración, los modelos de usuarios y módulos anteriores, sus formularios, rutas, plantillas y migraciones anteriores se conservaron. Las tablas nuevas incluyen `solicitud_id`, `version` y `usuario_modificacion_id` además de los campos solicitados, para prevenir dobles envíos, detectar ediciones simultáneas y conservar al creador.

## Validación automatizada

Se aprobaron **82 pruebas Python contra PostgreSQL real** y **12 pruebas JavaScript**, incluyendo las regresiones anteriores, creación y edición de ambos módulos, total inclusivo, días iguales, año bisiesto, fines de semana, cambio de año, total adulterado, fechas invertidas, restricciones SQL, filtros, orden, CSRF, roles y persistencia tras cerrar sesión y recrear la aplicación.

Para repetirlas, define `TEST_DATABASE_URL` con una conexión a una base dedicada cuyo nombre termine en `_test`. La suite limpia registros de prueba y modifica exclusivamente al administrador de esa base. Nunca uses la base de la aplicación como base de pruebas.

```powershell
.venv/Scripts/python.exe -m pytest -q
node --test tests/dashboard-ui.test.cjs tests/administration-ui.test.cjs tests/vacaciones-ui.test.cjs
```

Antes de aplicar la migración local se generaron un respaldo PostgreSQL y una copia de fuentes en `.runtime/backups/`. Después se compararon las cuentas, los triggers de protección y todos los registros previos de Justificativos y Cambios de Guardia: se conservaron. `flask db check` no detectó diferencias pendientes y `pip check` no detectó incompatibilidades.

También se verificaron por HTTP el login, las seis pantallas administrativas, sus formularios, los recursos estáticos, el reloj y el logout. No se crearon registros de ejemplo en la base de la aplicación. La revisión visual en navegador está pendiente si no hay un navegador conectado disponible en la sesión.
