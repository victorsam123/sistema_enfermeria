# Actualización 11 — Múltiples vínculos laborales

Cada cédula conserva **una sola ficha personal** y una fotografía principal. Los vínculos se guardan como filas relacionadas de `vinculos_laborales`, con fechas, estados e historial independientes. No se duplican funcionarios, expedientes, registros administrativos ni archivos.

## Instalar y migrar en Windows

1. Detén el servidor con Ctrl+C en su consola. Conserva `.env`, `instance/`, PostgreSQL y el almacenamiento privado existente.
2. Desde la carpeta del proyecto:

```powershell
Set-Location 'C:\Users\vi852\Desktop\Sistema de carga de documentos'
& .runtime/python/python.exe -s -m pip install -r requirements.txt
& .runtime/python/python.exe -s -m scripts.migrar_actualizacion11
& .runtime/python/python.exe -s -m flask --app run db check
```

Puedes usar el Python de tu `.venv` en lugar del portátil. No se añadieron dependencias: se reutiliza `python-dateutil`.

El script exige la revisión de la actualización 10 y crea un respaldo privado en `.runtime/backups/antes_actualizacion11_FECHA/`. Incluye `postgres.dump`, originales y vistas de fotografías activas/retiradas y un manifiesto SHA-256. Verifica el dump y los objetos **antes de migrar**. Si falla un respaldo o una fecha inicial es inválida, no continúa con cambios estructurales. Ejecuta el procedimiento con el servidor detenido.

La revisión nueva es **`0010_vinculos_laborales`**. `scripts.initialize` e `iniciar.ps1` también detectan esta transición y utilizan el respaldo. Reinicia normalmente:

```powershell
& .runtime/python/python.exe -s -m waitress --listen=127.0.0.1:5000 run:app
```

No ejecutes `drop_all`, reinicios de tablas ni restauraciones sobre la base de uso. La actualización no modifica el login, roles anteriores, contraseña ni protección de `victor`, catálogo de servicios, documentos o módulos administrativos existentes.

## Migración de fichas anteriores

- Cada **fecha exacta inicial existente** se conserva como vínculo n.º 1. Se copian el funcionario, fecha de ingreso, creador y fechas de auditoría de origen.
- La columna anterior `funcionarios.fecha_ingreso` permanece como referencia inicial histórica. Editar el vínculo 1 no destruye ese valor anterior.
- El contador manual anterior se copia a `cantidad_vinculos_declarada`, que queda protegido frente a cambios. La ficha permite consultar esa referencia.
- El nuevo `cantidad_vinculos` se calcula con los vínculos activos efectivamente registrados. Si antes figuraban tres vínculos pero solo existía una fecha, se crea **uno**, se conserva la declaración de tres y se solicita completar las fechas restantes.
- El contador anterior no era un estado laboral. Incluso si declaraba cero, una fecha inicial válida genera un vínculo 1 activo; la declaración de cero se conserva para revisión. Si corresponde inactivarlo, una cuenta autorizada puede hacerlo expresamente con motivo e historial. No se deduce una fecha de egreso ni una baja a partir del número anterior.
- No se inventan fechas o vínculos 2 y 3, ni se asocian personas por nombres. Las relaciones anteriores con los módulos administrativos y la fotografía se conservan.

Antes de finalizar, el script compara las columnas anteriores y los historiales, verifica el archivo del contador anterior y comprueba que cada ficha migrada tenga exactamente su vínculo 1 con la fecha original. Las nuevas auditorías de migración se agregan sin reemplazar eventos previos. Repetir la inicialización no genera más vínculos.

## Uso desde la ficha

1. Busca al funcionario por su cédula en **Funcionario**, como antes.
2. En la misma ficha aparece **VÍNCULOS LABORALES**. Cada tarjeta muestra número, estado, fecha exacta, año y antigüedad.
3. Pulsa **+ AGREGAR OTRO VÍNCULO**. El sistema propone el siguiente número libre y lo confirma en PostgreSQL al guardar. No es editable ni se reutilizan números inactivos.
4. Selecciona la fecha DD/MM/AAAA. El año y la antigüedad son de solo lectura; la vista previa consulta Python con CSRF y el calendario de Paraguay.
5. Guarda. Se agrega otra fila laboral a la misma ficha, sin otra cédula o fotografía. Un reenvío del mismo formulario no duplica el vínculo.
6. **EDITAR FECHA** corrige únicamente ese vínculo. **DESACTIVAR VÍNCULO** solicita motivo y confirmación; conserva su fila e historial. También se permite reactivar una baja administrativa errónea, dejando otro evento.

No hay un máximo de tres vínculos definido en el código. Fechas iguales pueden corresponder a vínculos distintos y son válidas; el número es único por funcionario. Distintos funcionarios pueden tener vínculo 1, vínculo 2, etc.

Al registrar una ficha nueva se solicita la fecha de su primer vínculo y se crea el vínculo 1 activo en la misma transacción. El total es de solo lectura. Los siguientes se agregan desde la ficha. Al editar datos personales ya no se utiliza un campo global de fecha para cambiar las fechas laborales; se usa **EDITAR FECHA** en la tarjeta correspondiente.

## Cálculo y total automático

Se reutiliza `dateutil.relativedelta` con la fecha actual en `America/Asuncion`; la zona del dispositivo no determina los resultados. Al 22/10/2026:

| Ingreso | Antigüedad |
|---|---|
| 10/03/2015 | 11 años, 7 meses y 12 días |
| 15/06/2020 | 6 años, 4 meses y 7 días |
| 01/02/2024 | 2 años, 8 meses y 21 días |

No se almacenan antigüedades fijas ni se dividen días por 30/365. Se recalcula al consultar la ficha y al cambiar la fecha del formulario. La ficha abierta conserva la recarga por cambio del día institucional. Si JavaScript está desactivado, el cálculo sigue efectuándose en Python al guardar y consultar.

Se exige una fecha completa, no futura y no anterior al nacimiento. Un año aislado no se convierte en enero ni en otra fecha inventada. El año de ingreso se obtiene de cada fecha. Corregir el nacimiento tampoco puede invalidar las fechas laborales ya registradas.

`TOTAL DE VÍNCULOS ACTIVOS` cuenta únicamente filas con `activo=true`. Triggers PostgreSQL sincronizan el contador de la ficha y una restricción diferida verifica el total antes del commit. Los campos enviados manualmente por un cliente no controlan el número, total, año o antigüedad. Todos los vínculos pueden quedar inactivos y el total será cero sin eliminar la ficha.

En tarjetas inactivas se mantiene la referencia de calendario desde su ingreso hasta hoy, claramente marcada como inactiva. Sin fecha de egreso no se afirma que esa diferencia sea tiempo efectivo trabajado.

## Un solo expediente y documentos

La ficha sigue mostrando una sola fotografía. Debajo de los vínculos se incorporan apartados para Justificativos, Reposos, Guardia normal, Guardia pagada, Vacaciones y Comisionados. Muestran los registros vinculados expresamente mediante el ID del funcionario y sus documentos originales; no se copian archivos ni registros. Se ocultan los registros eliminados lógicamente, como en las consultas anteriores.

Las filas históricas sin relación explícita permanecen en sus módulos y servicios. No se incorporan al expediente por coincidencia de nombres. La vista de registros reutiliza la tabla y la galería autorizadas existentes.

Se prepara `documentos_vinculos_laborales`, una tabla de referencias entre un documento ya almacenado y uno o varios vínculos del mismo funcionario. Una FK conserva cada extremo y un trigger impide asociar el archivo de otra persona. No duplica objetos físicos. La interfaz para asignaciones documentales específicas por vínculo queda reservada a la definición posterior de ese proceso; la gestión documental actual sigue operativa.

Los originales y versiones retiradas continúan en el almacenamiento privado local/S3 de la actualización 9. Los comandos de respaldo y conciliación existentes incluyen sus objetos; el dump incluye las nuevas relaciones:

```powershell
& .runtime/python/python.exe -s -m scripts.respaldar_documentos
& .runtime/python/python.exe -s -m flask --app run conciliar-documentos --verificar
```

El bucket S3 todavía no está configurado por el usuario. El almacenamiento privado local se conserva; para Railway sigue siendo necesario S3 o un volumen persistente declarado. No se cambia la configuración ni se trasladan imágenes durante esta actualización.

## Permisos, auditoría y concurrencia

Superadministrador y Jefatura pueden consultar, agregar, editar fechas, desactivar/reactivar vínculos y consultar el historial. Operador y Supervisor conservan la búsqueda mínima desde formularios administrativos; no tienen acceso a fichas completas, vínculos, su cálculo privado o expedientes. Las rutas GET/POST verifican los permisos centrales `employment.read/manage/history` y los de ficha/registros correspondientes, además de CSRF en los formularios y la vista previa.

Los vínculos tienen FK a la ficha y usuarios, número positivo único por funcionario, UUID de envío y versión. Las cargas se serializan mediante bloqueo de la ficha para evitar números repetidos. Una edición obsoleta devuelve 409 y pide recargar, sin sobrescribir otro cambio. Una doble confirmación de estado no reactiva accidentalmente una desactivación: la acción se envía expresamente.

PostgreSQL protege la identidad, número y auditoría inicial de cada vínculo, rechaza fechas inválidas, exige responsable y motivo para cambios de estado, y bloquea DELETE/TRUNCATE. No existen rutas de borrado físico. Las correcciones usan actualización y desactivación lógica.

El historial de la ficha agrega eventos con usuario, funcionario, vínculo, número, fecha/hora, fecha de ingreso anterior/nueva y estados anterior/nuevo. Muestra las fechas como DD/MM/AAAA. Las actualizaciones laborales también marcan el último responsable de la información institucional. La auditoría se genera en PostgreSQL en la misma transacción, sin registrar contraseñas, domicilios ni nacimiento en las descripciones de vínculos.

## Pruebas manuales

1. Busca una ficha migrada: debe mostrar vínculo 1, fecha original y referencia del contador anterior cuando exista.
2. Agrega vínculos 2 y 3 con las fechas del ejemplo. Verifica sus tres antigüedades y el total activo 3, dentro de la misma ficha y fotografía.
3. Edita solo la fecha del vínculo 2. Comprueba que 1 y 3 no cambien y que el historial muestre valor anterior, nuevo y responsable.
4. Desactiva el vínculo 2 con motivo. Debe conservarse como inactivo y el total pasar a 2. Reactívalo para corregir la baja; debe volver a 3 con otro evento.
5. Agrega un cuarto vínculo; los números anteriores, incluidos inactivos, no deben reutilizarse. Una segunda ficha debe comenzar su propia numeración en 1.
6. Prueba año sin fecha completa, fechas futuras/anteriores al nacimiento, ausencia de CSRF, confirmación vacía y formularios de edición abiertos antes de otro cambio.
7. Desde Operador/Supervisor intenta acceder directamente a alta/edición/estado/vista previa y expediente: deben rechazar la operación sin modificar filas.
8. Cierra sesión y reinicia conservando PostgreSQL y almacenamiento. Deben permanecer ficha, vínculos, fechas, foto y auditoría.
9. Abre apartados del expediente y galerías. Deben contener solo registros asociados a esa ficha y reutilizar los mismos documentos. Revisa también los módulos, servicios y Excel anteriores.

Las pruebas automatizadas exigen una base `TEST_DATABASE_URL` terminada en `_test`. La limpieza privilegiada de fixtures solo se permite allí; no existe un procedimiento de borrado equivalente en las rutas de la aplicación.

```powershell
& .runtime/python/python.exe -s -m pytest -q
node --test tests/*.test.cjs
```

El paquete completo es `entregables/fuentes_actualizacion11.zip`, con inventario en `entregables/ARCHIVOS_ACTUALIZACION_11.md`. Excluye credenciales, bases de datos, fotografías y respaldos privados. Consulta `VALIDACION.md` para los resultados efectivamente comprobados.
