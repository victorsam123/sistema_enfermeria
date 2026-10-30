# Actualización 5 · Reposo

El registro de Reposo está implementado en la aplicación existente y disponible en **http://127.0.0.1:5000/reposo/**. Se revisó la foto 3 y se conservaron sus seis columnas, adaptadas al diseño oscuro institucional. Los nombres y datos de la foto no se importaron a PostgreSQL.

## Funcionalidad

Desde el botón **Reposo** del Dashboard se abre el formulario con nombres y apellidos, fecha desde, fecha hasta, total calculado, diagnóstico y fecha de entrega al Departamento. Los campos de texto y las tres fechas son obligatorios. Las fechas se muestran como `DD/MM/AAAA` y admiten calendario o escritura.

El total es de solo lectura y cuenta días calendario incluyendo ambos extremos. El 01/10/2026 al 02/10/2026 equivale a **2** días, y el 16/10/2026 al 29/10/2026 a **14**. Una fecha única equivale a un día. Python recalcula el total al guardar o editar; el valor enviado por el navegador se ignora. PostgreSQL también comprueba la coherencia entre fechas y total. Se rechaza una fecha hasta anterior a la fecha desde.

La entrega al Departamento debe ser una fecha válida. No se impusieron condiciones adicionales sobre su relación con el inicio o final del reposo, porque no fueron solicitadas.

El formulario ofrece **GUARDAR REPOSO**, **CANCELAR**, **VER REGISTROS** y **VOLVER AL DASHBOARD**. Tras guardar aparece «Reposo registrado correctamente», el formulario queda limpio y la tabla se actualiza. Cancelar abre un formulario limpio; durante una edición descarta los cambios pendientes y vuelve al módulo.

Debajo se muestran los registros con las seis columnas solicitadas, una acción de edición y los datos del responsable de carga. Se puede buscar por nombre, filtrar períodos y ordenar por fecha desde o por fecha de creación, en ambos sentidos. El filtro incluye períodos que se superponen total o parcialmente con el rango seleccionado; por ejemplo, un reposo del 16/10 al 29/10 aparece al buscar el 20/10.

La paginación permite consultar todos los registros, hasta 20 por página, conservando búsqueda, fechas y orden. Los accesos anteriores a Cambio de Guardia y Cambio de Guardia Pagada siguen en esta pantalla y en la navegación lateral, con sus mismas rutas y registros.

## Actualizar otra instalación en Windows

La migración ya está aplicada en esta computadora. En otra instalación existente:

1. Conserva `.env`, la base PostgreSQL y sus datos. Crea un respaldo PostgreSQL y una copia de las fuentes actuales. No reemplaces `.runtime/pgdata` con la carpeta de otra computadora.
2. Detén únicamente la aplicación Flask/Waitress con Ctrl+C, copia las fuentes actualizadas y conserva la configuración local. No se añadieron dependencias.
3. Aplica la migración y reinicia la aplicación desde la carpeta del proyecto:

```powershell
.venv/Scripts/python.exe -m flask --app run db upgrade
.venv/Scripts/python.exe -m flask --app run db check
.venv/Scripts/python.exe -m waitress --listen=127.0.0.1:5000 run:app
```

Con el Python portátil de esta computadora:

```powershell
.runtime/python/python.exe -s -m flask --app run db upgrade
.runtime/python/python.exe -s -m flask --app run db check
.runtime/python/python.exe -s -m waitress --listen=127.0.0.1:5000 run:app
```

4. Recarga el Dashboard y abre Reposo con la contraseña vigente del administrador.

La migración `0004_reposos` sucede a `0003_comisionados_vacaciones` y añade únicamente `reposos`, con sus índices, claves foráneas y restricciones. No modifica tablas anteriores ni inicializa cuentas. No requiere `init-admin`, contraseñas iniciales ni recreación de la base. Repetir `db upgrade` no duplica registros ni tablas. El downgrade destructivo está bloqueado para conservar la información.

En producción con roles PostgreSQL separados, aplica la migración con el propietario del esquema y concede a la cuenta de ejecución SELECT/INSERT/UPDATE sobre `reposos` y USAGE/SELECT sobre su secuencia. Conserva sus permisos anteriores; no necesita permisos de eliminación ni de modificación del esquema.

## Pruebas manuales

1. Inicia sesión y comprueba los cinco accesos del Dashboard y el reloj de Paraguay.
2. Abre **Reposo**. Completa un nombre de prueba, las fechas 01/10/2026 y 02/10/2026, un diagnóstico y la fecha de entrega. El total debe mostrar 2 y no admitir escritura.
3. Cambia las fechas al 16/10/2026 y 29/10/2026: debe actualizarse a 14. Prueba también el mismo día en ambos campos: debe resultar 1.
4. Prueba una fecha hasta anterior, una fecha imposible, un nombre vacío, un diagnóstico vacío y una entrega vacía: debe rechazarse el guardado. El nombre admite entre 3 y 180 caracteres y el diagnóstico entre 1 y 2000, excluyendo espacios vacíos.
5. Guarda un registro legítimo. Debe aparecer «Reposo registrado correctamente», una fila con todas las columnas, el responsable y la hora de carga. El formulario debe quedar limpio.
6. Busca parte del nombre y filtra un día dentro del período. Cambia entre los cuatro órdenes disponibles. Usa las páginas siguientes si hay más de 20 registros.
7. Pulsa **Editar**, cambia la fecha hasta y guarda. El total debe recalcularse y deben mostrarse el editor y la fecha de modificación, conservando al creador y la fecha de creación.
8. Abre el mismo registro en dos pestañas, guarda en una e intenta guardar la otra. El segundo envío debe pedir recargar para evitar sobrescribir una edición más reciente.
9. Cierra sesión y vuelve a entrar: el reposo debe permanecer. Reiniciar únicamente la aplicación también debe conservarlo.
10. Comprueba Justificativo, ambos cambios de guardia, Vacaciones y Comisionados: mantienen sus funciones anteriores.

Las pruebas manuales con datos ficticios deben hacerse en una base de pruebas. No se cargaron registros de ejemplo en la base de la aplicación durante esta entrega.

## Seguridad y persistencia

Las rutas `/reposo/` y `/reposo/<id>/editar` requieren sesión y rol Superadministrador. Los POST requieren CSRF. El usuario creador se obtiene de la sesión, no del formulario. Las consultas usan SQLAlchemy y los textos se muestran escapados. Los diagnósticos y demás campos personales no se escriben en los logs de error.

Cada formulario lleva una clave UUID con unicidad en PostgreSQL para evitar cargas duplicadas por reenvío. Un formulario nuevo permite una carga legítima con datos iguales. La edición usa un contador de versión para detectar envíos obsoletos y registra al último editor. No se implementaron rutas ni botones de eliminación permanente.

Además de los campos mínimos solicitados, `reposos` incluye `solicitud_id`, `version` y `usuario_modificacion_id` para estas protecciones. Las horas de auditoría se guardan con zona horaria en UTC y se muestran en `America/Asuncion`; las fechas del reposo y de entrega son fechas locales sin conversión de zona.

## Archivos entregados

Nuevos:

```text
app/models/reposos.py
app/administration/reposos/forms.py
app/administration/reposos/rules.py
app/administration/reposos/views.py
app/static/css/reposos.css
app/static/js/reposos.js
migrations/versions/0004_reposos.py
tests/test_reposos.py
tests/reposos-ui.test.cjs
ACTUALIZACION_5.md
```

Modificados:

```text
app/administration/reposo.py            Integra formulario y edición al Blueprint existente
app/administration/reposos/__init__.py  Actualiza la descripción del paquete antes reservado
app/templates/administration/reposo.html Formulario, tabla y accesos previos a guardias
README.md
VALIDACION.md
```

No fue necesario cambiar el login, la configuración, el Dashboard, los modelos anteriores ni las rutas y formularios de los demás módulos. La carga de modelos para las migraciones ocurre mediante el Blueprint Reposo que la factoría ya registraba.

## Validación automatizada

Se aprobaron **105 pruebas Python contra PostgreSQL real** y **19 pruebas JavaScript**, incluidas todas las pruebas anteriores. Se verificaron los dos ejemplos de la foto, un solo día, año bisiesto, cambio de año, total adulterado, campos obligatorios, fechas imposibles, edición y conflictos de versión, filtros, orden, paginación, dobles envíos, permisos, CSRF y persistencia tras cerrar sesión y recrear la aplicación.

Para repetirlas, configura `TEST_DATABASE_URL` con una base dedicada terminada en `_test`. La suite modifica exclusivamente sus registros y su administrador de pruebas; no la apuntes a la base de la aplicación.

```powershell
.venv/Scripts/python.exe -m pytest -q
node --test tests/dashboard-ui.test.cjs tests/administration-ui.test.cjs tests/vacaciones-ui.test.cjs tests/reposos-ui.test.cjs
```

Antes de migrar se crearon una copia de las fuentes anteriores y un respaldo PostgreSQL en `.runtime/backups/`, excluidos del paquete de código. Tras migrar se compararon las cuentas, hashes, triggers y todos los registros anteriores de Justificativos, Cambios de Guardia, Comisionados y Vacaciones: se conservaron. `db check` y `pip check` no detectaron diferencias ni incompatibilidades.

La comprobación HTTP verificó el formulario de Reposo, campos y ordenamientos, los accesos de guardia, los módulos anteriores, recursos estáticos, reloj y cierre de sesión. No hay navegador conectado disponible para revisar visualmente el resultado; esa revisión permanece pendiente.
