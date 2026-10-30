# Actualización 3 · Registros administrativos

Esta ampliación conserva el login, las sesiones, `.env`, el reloj Paraguay y la cuenta protegida `victor`. En esta computadora ya se aplicó la migración `0002_administrative_records` y la aplicación está disponible en **http://127.0.0.1:5000**.

## Funciones disponibles

- **Justificativo:** formulario, listado paginado, búsqueda por nombre, rango de fechas de inasistencia y edición para Superadministrador. Muestra responsable y fecha de creación; las modificaciones conservan al creador e identifican al último editor. No hay acciones de eliminación.
- **Reposo:** pantalla con los dos accesos solicitados. No incluye formulario de reposo médico.
- **Cambio de Guardia:** registro y consulta de categoría `NORMAL`.
- **Cambio de Guardia Pagada:** registro y consulta independiente de categoría `PAGADA`, sin importes ni funciones económicas.
- El acceso **Cambio de Guardia** del Dashboard usa exactamente la misma ruta que el de Reposo. Vacaciones y Comisionados mantienen su aviso de desarrollo.

La estructura de datos sigue los campos definidos en el texto. Tras recibir las fotos 1 y 2, la presentación de ambas tablas se adaptó a sus planillas: solicitante agrupado en una celda, fechas y nombres por líneas, columna estrecha de identificación y horario compartido por cada par S/R. Cada registro conserva su ID, responsable y fecha de carga. Los códigos G y L no se almacenan ni interpretan: podrán agregarse con una migración cuando se defina su significado.

## Aplicar en otra instalación existente de Windows

1. Conserva el archivo `.env` y la base PostgreSQL actuales. Realiza una copia de seguridad mediante pgAdmin o `pg_dump` antes de actualizar. No copies `.runtime/pgdata` desde otra computadora ni reemplaces la base existente.
2. Copia los archivos del proyecto actualizado. No necesitas cambiar las dependencias para esta ampliación.
3. Detén únicamente el proceso Flask/Waitress, con Ctrl+C en su terminal. No es necesario detener PostgreSQL.
4. Desde la carpeta del proyecto ejecuta:

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

`db upgrade` añade `justificativos` y `cambios_guardia`. No ejecuta la inicialización de `victor`, no cambia contraseñas y no modifica las tablas anteriores. La migración tiene como antecesora `0001_initial`. Repetir `db upgrade` no vuelve a crear las tablas. Los downgrades destructivos se rechazan para conservar registros.

En una instalación de producción con roles PostgreSQL separados, aplica la migración con el propietario de migraciones. Después concede a la cuenta de ejecución SELECT/INSERT/UPDATE de `justificativos`, SELECT/INSERT de `cambios_guardia`, y USAGE/SELECT de sus secuencias. Conserva sus permisos anteriores. No otorgues permisos para eliminar estos registros ni modificar el esquema.

## Cómo probar cada apartado

### Justificativo

1. Inicia sesión con la contraseña vigente del administrador y abre **Justificativo**.
2. Completa nombres, fecha de inasistencia, motivo y fecha de cobertura. Las fechas se escriben como `DD/MM/AAAA`; el ícono de calendario permite seleccionarlas. El motivo admite hasta 2000 caracteres.
3. Pulsa **GUARDAR JUSTIFICATIVO**. Debe aparecer «Justificativo registrado correctamente», el registro en la tabla y un formulario nuevo limpio.
4. Busca una parte del nombre y usa los filtros **Desde/Hasta**. El rango incluye ambas fechas y se aplica a la fecha de inasistencia.
5. Pulsa **Editar** en la fila, modifica un campo y guarda. Deben conservarse el creador y la fecha de creación, mostrando también al editor y la fecha de modificación.
6. Abre una edición en dos pestañas. Guarda en una e intenta guardar la otra: la segunda debe pedir recargar para revisar la versión actual, sin sobrescribirla.

### Reposo y cambios de guardia

1. Entra a **Reposo**: deben aparecer **CAMBIO DE GUARDIA** y **CAMBIO DE GUARDIA PAGADA**.
2. En Cambio de Guardia ingresa un solicitante (S), un reemplazante (R) distinto, una fecha y un horario, por ejemplo `18:00` a `06:00`.
3. Guarda y comprueba la confirmación y la fila en la tabla. El horario debe mostrar que finaliza al día siguiente, con su fecha correspondiente.
4. Registra otro cambio en la categoría pagada. Al volver a la categoría normal, el registro pagado no debe aparecer allí, y viceversa. El campo `tipo_cambio` lo determina el servidor según la ruta; no se acepta una categoría enviada por el cliente.
5. **VER REGISTROS** lleva a la tabla de la misma categoría. Los filtros por nombre y fecha son independientes en cada pantalla. La paginación muestra hasta 20 registros por página.

   Las tablas muestran hasta 20 **registros** por página; cada uno ocupa dos líneas, S y R. Los registros de un mismo solicitante se agrupan visualmente dentro de esa página. Este agrupamiento no fusiona registros ni identifica personas mediante un nombre único. El horario y la información de carga pertenecen al par S/R. La adaptación a las fotos conserva los colores oscuros y celestes institucionales y no necesita migraciones adicionales.
6. El botón **Cambio de Guardia** del Dashboard debe llevar a la misma pantalla normal. **CANCELAR** vuelve al Dashboard o a Reposo sin guardar.

### Validaciones y persistencia

- Prueba un campo vacío, una fecha inexistente, horas iguales o el mismo nombre para solicitante y reemplazante: no debe guardarse el registro. Las horas iguales se rechazan porque no distinguen duración cero de un turno de 24 horas; un fin anterior al inicio representa el día siguiente.
- Cierra sesión y vuelve a entrar: los registros deben seguir disponibles. Reiniciar únicamente la aplicación también debe conservarlos.
- Un doble clic o reenvío del mismo formulario no debe crear dos filas. Cada formulario recibe una clave de envío UUID con unicidad en PostgreSQL. Un formulario nuevo puede guardar datos iguales si corresponde a una carga legítima; no se impone unicidad por nombre o fecha.
- Un envío con la misma clave pero con datos distintos se rechaza; el formulario permite revisar los datos e intentar una carga nueva.
- Las páginas nuevas requieren autenticación y rol Superadministrador. Los POST requieren CSRF. No existen rutas de eliminación. Los textos se muestran escapados y las consultas usan parámetros SQLAlchemy.
- Las fechas de registro se almacenan con zona horaria en UTC y se muestran en `America/Asuncion`. Las fechas de ausencia/cambio/cobertura y las horas de guardia representan el calendario y horario local, sin conversión de zona.

## Archivos de la ampliación

Nuevos:

```text
app/administration/__init__.py
app/administration/forms.py
app/administration/services.py
app/administration/justificativos.py
app/administration/reposo.py
app/administration/guardias.py
app/models/administration.py
app/templates/includes/sidebar.html
app/templates/includes/header.html
app/templates/includes/clock.html
app/templates/administration/base.html
app/templates/administration/macros.html
app/templates/administration/justificativos.html
app/templates/administration/reposo.html
app/templates/administration/guardias.html
app/static/css/administration.css
app/static/js/administration.js
migrations/versions/0002_administrative_records.py
tests/test_administration.py
tests/administration-ui.test.cjs
ACTUALIZACION_3.md
```

Modificados:

```text
app/__init__.py                 Solo registra los módulos nuevos
app/dashboard_modules.py        Vincula tres tarjetas a sus Blueprints
app/templates/base.html         Añade un bloque para recursos de cada módulo
app/templates/dashboard.html    Reutiliza encabezado, menú y reloj compartidos
app/static/css/app.css          Permite desplazamiento del menú lateral
tests/test_auth.py              Verifica los accesos ahora habilitados
README.md
VALIDACION.md
```

Los componentes de autenticación, configuración, modelo Usuario y migración inicial no fueron modificados.

## Pruebas automatizadas

Usa exclusivamente una base PostgreSQL destinada a pruebas, cuyo nombre termine en `_test`. La suite limpia registros administrativos de esa base e inicializa su propio administrador de pruebas; nunca la apuntes a la base de la aplicación. Configura `TEST_DATABASE_URL` mediante una variable de entorno local, sin publicar credenciales.

```powershell
.venv/Scripts/python.exe -m pytest -q
node --test tests/dashboard-ui.test.cjs tests/administration-ui.test.cjs
```

En esta actualización se aprobaron **48 pruebas Python** y **5 pruebas JavaScript**, incluyendo creación, filtros, edición, conflicto de versiones, persistencia al recrear la aplicación, turnos nocturnos, separación de categorías, CSRF, autorización y doble envío concurrente. También se verificó HTTP contra la aplicación en ejecución sin crear registros ficticios en su base.

Antes de migrar la base de esta computadora se creó un respaldo PostgreSQL y una copia de las fuentes previas en `.runtime/backups/`, que no se incluyen en el código distribuido. Tras migrar se comprobaron las cuentas y los triggers de protección existentes. `db check` no detectó diferencias pendientes entre los modelos y las migraciones.

No hay navegador conectado disponible para la revisión visual de los formularios. La validación incluye HTML renderizado por Flask, recursos estáticos por HTTP y comportamiento JavaScript probado con Node.js.

Referencias técnicas: [inserción con ON CONFLICT en SQLAlchemy/PostgreSQL](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert) y [control de versiones de SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/versioning.html).
