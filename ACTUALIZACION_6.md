# Actualización 6 · Navegación, guardias con múltiples fechas y cobertura opcional

Las correcciones están aplicadas en la aplicación existente: **http://127.0.0.1:5000**. Se revisó `foto 4.png` y se mantuvieron los códigos originales sin asignar significados a G o L. Los nombres y datos de la imagen no se cargaron como registros de ejemplo.

## Navegación corregida

En Cambio de Guardia y Cambio de Guardia Pagada, **VOLVER AL PANEL PRINCIPAL** utiliza `url_for('main.dashboard')` y regresa a `/`, conservando la sesión. Se retiró el enlace confuso «Volver a Reposo» de esas pantallas. El encabezado compartido de los módulos también utiliza el texto correcto y la ruta del Dashboard. Los demás accesos mantienen sus destinos, y CANCELAR limpia una carga nueva o sale de una edición sin guardar.

## Cambios de guardia con fechas independientes

El formulario mantiene dos funcionarios relacionados con una única operación:

- **Sección A:** solicitante (S), fecha de guardia, hora de inicio, hora de finalización y código opcional.
- **Sección B:** reemplazante (R), con su propia fecha, horario y código opcional.

Las fechas y horarios pueden coincidir o ser diferentes. Un fin anterior al inicio corresponde al día siguiente respecto de la fecha de esa fila. Las horas iguales se rechazan para evitar un horario ambiguo.

**+ AGREGAR OTRA FECHA** incorpora más filas, cada una con participante, fecha, inicio, fin y código. La selección del participante muestra los nombres del solicitante y del reemplazante. No existe un límite de dos fechas: se verificó el guardado de **120 filas** en una única operación. Las filas se guardan juntas, en una sola transacción.

Una anotación `02-08/10/2026` no se interpreta como período. Carga una fila para `02/10/2026` y otra para `08/10/2026`. El formato abreviado no es una fecha válida del formulario. Para incluir el 17/10, agrega una tercera fila con esa fecha.

La columna `participante` distingue S y R, independientemente de `codigo`. Los códigos disponibles son G, L, S, R o vacío. G y L son únicamente valores literales; no se aplican reglas institucionales ni cálculos derivados de ellos.

### Consulta y edición

Cada bloque de la tabla corresponde a un **ID de cambio**, muestra ambos funcionarios, responsable, fechas, códigos y horarios por fila. Dos cambios con los mismos nombres permanecen en bloques separados. Los horarios ya no se comparten obligatoriamente entre todas las fechas.

La búsqueda consulta a cualquiera de los funcionarios. El filtro de fechas encuentra operaciones que tengan al menos una fecha específica dentro del rango inclusivo y muestra todas las filas de esa operación, para conservar su contexto. La paginación muestra hasta 20 operaciones por página sin dividir un cambio entre páginas.

**Editar / agregar fechas** permite corregir nombres, fechas, horarios y códigos o incorporar nuevas filas a un cambio ya guardado. Se conservan los IDs de sus detalles y el creador original. La última modificación identifica al editor y actualiza su fecha. La versión del registro impide sobrescribir una edición concurrente.

Se pueden quitar filas nuevas todavía sin guardar. Las fechas ya guardadas se conservan y pueden corregirse; no se añadió eliminación permanente. No se acepta un detalle perteneciente a otro cambio ni la omisión de fechas guardadas al editar. Las secciones iniciales mantienen la relación S/R.

Las cargas duplicadas con la misma clave de envío no crean otro cambio ni otras fechas. También se rechazan filas exactamente repetidas dentro de una operación: mismo participante, fecha, horario y código. Un formulario nuevo puede registrar una operación independiente legítima con datos coincidentes.

Los formularios antiguos de una sola fecha que hayan quedado abiertos durante la actualización se convierten, al crear, en las mismas dos filas S/R con su fecha y horario originales. La interfaz vigente utiliza únicamente la estructura nueva.

## Justificativo sin cobertura

La fecha de cobertura es **opcional** en el formulario y admite `NULL` en PostgreSQL. Nombre, fecha de inasistencia y motivo siguen siendo obligatorios.

- Cobertura vacía: se guarda `NULL` y la tabla muestra **SIN COBERTURA**.
- Cobertura seleccionada: se guarda y muestra la fecha en `DD/MM/AAAA`.
- Cobertura no vacía pero inválida: se rechaza el formulario.

No se asignan fechas ficticias ni la fecha actual. La edición permite agregar, cambiar o quitar la cobertura de un justificativo, conservando su auditoría. Las fechas anteriores no se modificaron por la migración.

## Migración y conservación de datos

`0005_guardias_fechas_y_cobertura` sucede a `0004_reposos` y realiza únicamente estos cambios:

1. Permite `NULL` en `justificativos.fecha_cobertura`.
2. Añade editor y versión a `cambios_guardia`.
3. Crea `detalles_cambio_guardia`, con clave foránea al cambio, participante, funcionario, fecha, horas, código y orden.
4. Por cada cambio existente crea dos detalles S/R, copiando exactamente sus nombres, fecha y horario. Verifica la copia antes de finalizar.
5. Añade restricciones para códigos, horarios, duplicados y coherencia entre participantes y fechas de la operación.

**No elimina `fecha_cambio`, `hora_inicio` ni `hora_fin` de la tabla principal.** Sus valores anteriores se conservaron íntegramente. En operaciones nuevas representan la referencia inicial de la sección A; las consultas y ediciones vigentes utilizan los detalles asociados. Editar las fechas no sobrescribe esas columnas anteriores. Su retiro futuro requerirá una decisión y otra migración, después de validar y respaldar los datos.

No se recrearon tablas ni se borraron registros. No se modificaron cuentas, contraseñas, protecciones de `victor`, ni registros de Justificativo, Reposo, Vacaciones o Comisionados. El downgrade destructivo está bloqueado.

## Aplicar en otra instalación existente de Windows

En esta computadora ya se realizó el respaldo y se aplicó la migración. Para otra instalación:

1. Haz una copia de seguridad de PostgreSQL y de las fuentes actuales. Conserva `.env` y todos los datos.
2. Detén únicamente Flask/Waitress con Ctrl+C. Copia las fuentes actualizadas sin reemplazar la base ni `.runtime/pgdata`.
3. Ejecuta desde la carpeta del proyecto:

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

4. Recarga el Dashboard e ingresa con tu contraseña vigente. No ejecutes un restablecimiento de contraseñas ni recrees la base.

No se añadieron dependencias. En producción con roles separados, migra con el propietario del esquema y concede a la cuenta de ejecución SELECT/INSERT/UPDATE sobre `detalles_cambio_guardia`, USAGE/SELECT sobre su secuencia y los permisos anteriores sobre `cambios_guardia`. Conserva el acceso a las demás tablas. Las verificaciones transaccionales necesitan leer ambos lados de la relación; no hace falta conceder eliminación ni privilegios de modificación del esquema.

Para permitir cargas extensas, solo los POST del Blueprint guardias admiten cuerpos de hasta 2 MiB. La interfaz y el modelo no fijan una cantidad máxima de filas, aunque toda solicitud sigue sujeta a límites de seguridad del servidor. Los límites y la configuración de los otros módulos permanecen iguales. No se cambió `config.py`.

## Verificar las seis pruebas solicitadas

Realiza las cargas de ejemplo en una base de pruebas, sin introducir datos ficticios en los registros de la institución.

1. **Navegación:** inicia sesión, entra a Cambio de Guardia y pulsa VOLVER AL PANEL PRINCIPAL. Debes regresar al Dashboard y seguir autenticado. Repite en la categoría pagada.
2. **Fechas diferentes:** registra dos funcionarios distintos, fecha A `04/10/2026` con `18:00–06:00` y fecha B `05/10/2026` con `06:00–12:00`. Guarda. Ambas filas deben quedar bajo el mismo ID, y la primera debe indicar que finaliza al día siguiente.
3. **Varias fechas:** carga A el `02/10/2026`, B el `08/10/2026` y usa + AGREGAR OTRA FECHA para incorporar el `17/10/2026`. Deben aparecer tres fechas individuales, sin generar días intermedios. Edita el cambio y agrega otra fecha: las anteriores deben conservar sus IDs. Cambios independientes con los mismos funcionarios deben seguir en grupos separados.
4. **Sin cobertura:** guarda un justificativo con nombre, fecha de inasistencia y motivo, dejando cobertura vacía. La tabla debe mostrar SIN COBERTURA y PostgreSQL debe almacenar `NULL`.
5. **Con cobertura:** guarda otro justificativo con una cobertura válida. Debe mostrarse esa fecha; al editar puedes dejarla vacía si corresponde, sin fechas sustitutas.
6. **Persistencia:** cierra sesión y vuelve a entrar. Comprueba las filas, códigos, horarios, categorías y coberturas. Reiniciar únicamente la aplicación también debe conservarlos.

Comprueba además fechas imposibles, funcionarios iguales, horas iguales, filas repetidas y un código fuera de G/L/S/R: deben rechazarse sin guardar parcialmente la operación. La categoría normal y la pagada conservan sus consultas independientes. Reposo, Vacaciones y Comisionados siguen disponibles con sus mismas funciones.

## Archivos de esta actualización

Nuevos:

```text
app/administration/guardia_records.py
app/administration/guardia_limits.py
app/templates/administration/guardia_macros.html
app/static/css/guardias.css
app/static/js/guardias.js
migrations/versions/0005_guardias_fechas_y_cobertura.py
tests/test_guardias_multifecha.py
tests/guardias-ui.test.cjs
ACTUALIZACION_6.md
```

Modificados:

```text
app/models/administration.py
app/administration/forms.py
app/administration/guardias.py
app/templates/administration/base.html
app/templates/administration/macros.html
app/templates/administration/guardias.html
app/templates/administration/justificativos.html
app/static/css/administration.css
tests/test_administration.py
README.md
VALIDACION.md
```

## Pruebas y evidencia

Se aprobaron **127 pruebas Python contra PostgreSQL real** y **22 pruebas JavaScript**. Las pruebas nuevas cubren fechas y horarios distintos, varias fechas independientes, 120 filas en una operación, edición con nuevas fechas, IDs preservados, rechazo de IDs ajenos u omisiones, duplicados, envíos concurrentes, categorías, filtros, navegación, coberturas opcionales y persistencia. Una prueba migró datos anteriores dentro de un esquema aislado de la base de pruebas y comprobó la conservación de fechas, horarios y coberturas originales.

Se repitieron las 22 pruebas específicas de esta actualización tras la última revisión. Para repetir la suite usa exclusivamente `TEST_DATABASE_URL` dirigido a una base dedicada terminada en `_test`:

```powershell
.venv/Scripts/python.exe -m pytest -q
node --test tests/dashboard-ui.test.cjs tests/administration-ui.test.cjs tests/vacaciones-ui.test.cjs tests/reposos-ui.test.cjs tests/guardias-ui.test.cjs
```

La suite limpia únicamente registros de prueba. La prueba de migración crea un esquema independiente en esa base de pruebas y no elimina esquemas ni tablas de la aplicación.

Antes de actualizar la base real se generaron una copia de fuentes y un respaldo PostgreSQL en `.runtime/backups/`. Tras migrar se compararon todas las columnas originales de los registros anteriores, las cuentas, hashes y triggers de protección: conservados. Se verificó la conversión a detalles y `flask db check` no detectó diferencias pendientes. `pip check` no detectó incompatibilidades.

La comprobación HTTP validó navegación, formulario de guardias, cobertura opcional, módulos anteriores, recursos, reloj y logout. No se crearon registros de ejemplo en la base de la aplicación. La revisión visual permanece pendiente porque no hay un navegador conectado disponible.
