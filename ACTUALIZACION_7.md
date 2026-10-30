# Actualización 7 · Servicios hospitalarios e informes Excel

La actualización se integró a la aplicación existente en **http://127.0.0.1:5000**. Se conservaron el login, la cuenta protegida `victor`, las rutas de los módulos y sus datos. No se importaron registros del archivo Excel de referencia.

## Servicios y carpetas virtuales

La migración `0006_servicios_e_informes` crea el catálogo una sola vez, con códigos únicos y permanentes. Los nombres originales de las hojas se conservan para las exportaciones; solo se retiran los espacios finales que tenían algunas hojas del modelo.

| Servicio | Código permanente | Hoja principal Excel |
|---|---|---|
| UTI - P | UTI-P | UTI-P |
| Quirófano | QUIROFANO | QUIROFANO |
| UTI - A | UTI-A | UTI-A |
| Neonatología | NEONATOLOGIA | NEONATOLOGIA |
| Maternidad | MATERNIDAD | MATERNIDAD |
| PAI | PAI | PAI |
| Urgencia Trauma | URGE-TRAUMA | URGE-TRAUMA |
| Supervisión | SUPERVISION | SUPERVISION |
| Cirugía | CIRUGIA | CIRUGIA |
| Clínica | CLINICA | CLINICA |
| Pediatría Internación | PEDIATRIA_INTER | PEDIATRIA INTER |
| LAB - UMT | LAB-UMT | LAB-UMT |
| Pediatría Urgencia | PEDIATRIA_URGENCIA | PEDIATRIA URGENCIA |
| Salud Pública | SALUD_PUBLICA | SALUD PUBLICA |

`Hoja1` no se incorpora. Existe además la categoría protegida **PENDIENTE DE CLASIFICACIÓN**, exclusiva para los registros anteriores cuya procedencia todavía no se conoce.

Los cinco modelos principales tienen una FK `servicio_id` no nula hacia `servicios`, con restricción de borrado. Los detalles de guardia utilizan el servicio de su cambio principal. NORMAL y PAGADA conservan sus categorías. No se añadieron montos ni reglas para interpretar G o L.

En todos los formularios aparece **Servicio hospitalario**. Si se presiona GUARDAR sin elegirlo, se abre **¿EN QUÉ SERVICIO DESEA GUARDAR ESTE REGISTRO?**. CONFIRMAR Y GUARDAR conserva los datos ingresados, asigna el servicio y continúa con las validaciones normales. CANCELAR o Escape no guarda ni limpia los campos. Sin JavaScript se puede usar directamente el selector visible; el backend también exige la selección.

Flask solo admite servicios activos existentes. PostgreSQL rechaza nuevas filas sin servicio, con una FK inexistente, con un servicio inactivo o con la categoría pendiente. No se guarda una fecha ni un servicio ficticio. La confirmación identifica el servicio elegido.

**Archivos por Servicio** muestra una carpeta por servicio con registros, su cantidad total y la fecha de la última carga. Las carpetas se obtienen de las relaciones persistentes de PostgreSQL, sin duplicar datos y sin crear directorios físicos. Al abrirlas se muestran las seis categorías, con búsqueda, fechas, paginación y edición. Si se reclasifica el último registro de una carpeta, esta deja de aparecer en el listado de carpetas con movimientos; el servicio continúa en el catálogo.

Las tablas originales también muestran el servicio. Los registros pendientes se pueden consultar en su carpeta y clasificar mediante **Corregir servicio**. Editar un registro pendiente exige clasificarlo antes de guardar. Los servicios inactivos siguen disponibles para consultar y exportar sus datos anteriores; para nuevas cargas o para guardar una edición se debe elegir un servicio activo.

## Configuración e historial

El menú **Configuración de servicios**, exclusivo del Superadministrador, permite agregar servicios, modificar nombres y activar o desactivar. El código permanece fijo para conservar la identidad y el nombre de hoja asociado. No se ofrece eliminación física; PostgreSQL bloquea DELETE, TRUNCATE y el cambio de código del catálogo.

**Corregir servicio** cambia la clasificación sin volver a cargar el registro. Se registra usuario, fecha, entidad, ID y servicios anterior y nuevo en `historial_administrativo`. Cambiar el servicio desde la edición normal también deja ese historial. Se conservan el creador y la fecha original; se actualizan el editor, la fecha de modificación y la versión para detectar ediciones concurrentes.

El historial también incluye mantenimiento del catálogo, generación, vista previa y descarga de informes, con sus filtros. No guarda diagnósticos ni contraseñas. No se añadieron rutas para eliminar registros ni historial.

## Informes y criterios de selección

Desde **Informes Excel**, selecciona fechas DD/MM/AAAA, un servicio o TODOS LOS SERVICIOS y la categoría. GENERAR INFORME prepara la consulta y su vista previa. VISTA PREVIA permite revisarla. DESCARGAR EXCEL genera el archivo `.xlsx` en memoria y lo entrega como descarga autenticada.

La descarga vuelve a consultar los datos vigentes con los filtros seleccionados; no guarda una copia histórica de la vista previa. Cada operación utiliza un snapshot consistente de PostgreSQL para evitar mezclar clasificaciones durante una consulta concurrente. Las descargas no se guardan en `static`, no tienen enlaces públicos ni se imprimen automáticamente.

| Categoría | Fecha utilizada |
|---|---|
| Justificativos | Fecha de inasistencia, inclusiva |
| Reposos | Superposición: hasta ≥ desde del informe y desde ≤ hasta del informe |
| Guardia normal y pagada | Fechas individuales de sus detalles dentro del rango, inclusivas |
| Vacaciones | Superposición del período de vacaciones y el solicitado |
| Comisionados | Fecha de inasistencia, inclusiva |

Los reposos y vacaciones mantienen sus fechas y total original completo, aunque solo una parte coincida con el informe. Una guardia puede incluir solo algunas de sus fechas: las que quedan fuera del rango no se convierten en movimientos del período. Cada operación conserva su ID, ambos participantes y categoría, aunque alguna de sus filas quede fuera de la consulta. S/R y el código original se exportan por separado en los detalles.

La vista previa muestra hasta 20 registros por categoría y 20 fechas por cambio; el Excel incluye todos los registros seleccionados. Para evitar agotar memoria, un informe de más de 50.000 filas de movimientos se rechaza con una indicación para reducir el rango o seleccionar un servicio. No se trunca silenciosamente. El límite se puede ajustar mediante la configuración Flask `MAX_REPORT_ROWS`.

## Estructura del libro

El archivo de referencia se utiliza únicamente como modelo de hojas, distribución y estilo. El generador XlsxWriter no lo abre ni depende de tenerlo en el servidor.

- Una hoja principal por servicio, con encabezado institucional, nombre de servicio y período.
- Tres bloques conservados: **CAMBIO DE GUARDIA (A:E)**, **JUSTIFICATIVO (G:I)** y **REPOSO (K:P)**, con separadores F y J. Las guardias normales y pagadas están agrupadas por ID y rotuladas por tipo.
- Hojas complementarias cuando existen datos: `_JUST`, `_REPOSOS`, `_GUARDIAS`, `_PAGADAS`, `_VACACIONES` y `_COMISIONADOS`. Los nombres se acortan y distinguen automáticamente para no superar 31 caracteres ni repetirse.
- Justificativos conserva la fecha de cobertura en su hoja complementaria. Si está vacía se muestra SIN COBERTURA.
- Las hojas de detalle conservan campos administrativos, IDs, autor, editor, fechas de auditoría en Paraguay y versión. Las guardias incluyen además participante, código literal, horarios, fecha de finalización nocturna y valores originales de las columnas antiguas.
- TODOS LOS SERVICIOS incluye los 14 servicios iniciales, incluso sin movimientos, y cualquier servicio agregado posteriormente. Los inactivos conservan su hoja. La hoja PENDIENTE CLASIFICACION aparece si esa categoría tiene movimientos en el rango o si se selecciona expresamente.
- Sin movimientos se muestran títulos, columnas y **Sin registros en el período seleccionado**. Un tipo de informe específico conserva los tres bloques principales, indicando cuáles no se incluyeron, y su hoja complementaria con las columnas correspondientes.

Las fechas y horas son valores Excel tipados con formatos `dd/mm/yyyy` y `hh:mm`; los totales son numéricos. Los textos de las personas se escriben como texto literal: no se interpretan como fórmulas ni hipervínculos. Los encabezados amarillos, las bandas y los bordes siguen la referencia. Hay ajuste de texto, anchos de columna, encabezados congelados, orientación horizontal, A4, márgenes, títulos repetidos, área de impresión y ajuste al ancho de una página; la altura puede ocupar varias páginas.

En las hojas complementarias, el área de impresión incluye los campos del módulo y el ID de registro. La auditoría y los valores originales adicionales quedan a la derecha, disponibles en Excel, para evitar imprimirlos con una letra demasiado pequeña. En la hoja principal se imprimen los tres bloques. El administrador puede ajustar márgenes, escala o área desde Excel según la longitud de sus registros.

## Seguridad

Todas las rutas nuevas exigen autenticación y rol Superadministrador; la política de diagnósticos está centralizada en `can_view_diagnosis()`. Actualmente ese es el único rol autorizado para acceder a registros de salud y exportarlos. Agregar un rol futuro no concede acceso automáticamente.

Se conserva CSRF, cookies, protección de sesión, contraseñas con hash, consultas SQLAlchemy y control de versiones existente. Las descargas llevan Content-Disposition y Cache-Control: no-store. No se crean informes sensibles públicos ni carpetas físicas de registros. El catálogo y el historial no modifican las protecciones Python/PostgreSQL del usuario `victor`.

## Aplicación en Windows

En esta computadora la migración ya está aplicada y la aplicación está iniciada. Para revisar basta abrir **http://127.0.0.1:5000**. No vuelvas a crear la base ni cambies `.env`.

Para actualizar otra copia de la versión anterior, conserva su `.env`, la base y el historial de migraciones. Detén su servidor antes de estos comandos en PowerShell:

```powershell
& .runtime/python/python.exe -s -m pip install -r requirements.lock.txt
& .runtime/python/python.exe -s scripts/migrar_actualizacion7.py
& .runtime/python/python.exe -s -m flask --app run db check
& .runtime/python/python.exe -s -m waitress --listen=127.0.0.1:5000 run:app
```

Con instalación estándar sustituye el ejecutable por `.venv/Scripts/python.exe` y omite `-s` si lo prefieres. El script de migración requiere la revisión anterior `0005_guardias_fechas_y_cobertura` o la actual. Localiza `pg_dump`/`pg_restore` en PATH o en PostgreSQL 18; `PG_DUMP` permite indicar una ruta específica. Si el respaldo falla, no migra. Guarda un respaldo custom privado en `.runtime/backups`, verifica su catálogo, migra y compara todas las columnas anteriores de usuarios y registros y los triggers de protección.

`scripts.initialize` también utiliza este procedimiento con respaldo al detectar la revisión anterior, sin restablecer un administrador existente. Una instalación nueva sigue usando las migraciones normales. En un servicio remoto se requiere disponer de los clientes PostgreSQL y un destino privado persistente para conservar o retirar el respaldo antes de reemplazar una instancia efímera. Esta actualización no despliega en Railway ni cambia credenciales.

## Pruebas manuales

1. Ingresa con la cuenta administrativa existente. Abre Justificativo, completa sus campos y deja Servicio vacío. GUARDAR debe mostrar la pregunta; CANCELAR debe conservar el formulario. Confirma UTI - P y verifica la notificación y su carpeta.
2. Guarda otro justificativo en UTI - P y un reposo en Urgencia Trauma. Deben aparecer dos registros en una sola carpeta UTI - P y el reposo solamente en Urgencia Trauma. Verifica que no se permita guardar sin servicio.
3. Abre cada carpeta y sus seis categorías. Comprueba búsqueda, fechas, edición y regreso al panel. Cambio de Guardia y su categoría pagada deben seguir separados y admitir varias fechas.
4. En Configuración, modifica el nombre de un servicio y comprueba que conserva sus registros y código. Desactívalo: deja de poder seleccionarse para guardar, pero sus registros siguen consultables y exportables. Reactívalo al terminar la comprobación.
5. En la carpeta pendiente, utiliza Corregir servicio con una clasificación conocida. Comprueba la carpeta de destino y el evento anterior/nuevo en Historial administrativo. Repite la operación desde una edición normal si necesitas verificar ambos caminos.
6. En Informes selecciona UTI - P, 01/10/2026 a 30/10/2026 y completo. Revisa la vista previa y descarga. Comprueba los tres bloques y los complementos. Un reposo 28/09–05/10 debe aparecer con sus fechas originales; una guardia con fechas de septiembre y octubre solo aporta al período las de octubre.
7. Descarga TODOS LOS SERVICIOS y comprueba las hojas independientes, sin Hoja1 ni mezcla de datos. Repite para un rango sin movimientos y para cada categoría individual.
8. Desde Excel revisa Archivo → Imprimir sin enviar a una impresora: A4 horizontal, ajuste al ancho y encabezados. Las hojas adicionales conservan las columnas de auditoría fuera del área de impresión.
9. Cierra sesión y vuelve a entrar; reinicia solo el servidor. Catálogo, clasificación y registros deben conservarse. Sin sesión, las rutas de carpetas, configuración e informes deben redirigir al login; un rol no autorizado debe recibir 403.

Estas pruebas manuales crean registros reales si se ejecutan en la base de uso. Para practicar con datos ficticios utiliza únicamente una base dedicada terminada en `_test`, separada de la aplicación.

## Pruebas automatizadas y conservación

```powershell
# Define TEST_DATABASE_URL con una conexión a PostgreSQL exclusiva de pruebas,
# cuya base termine en _test. No uses DATABASE_URL de la aplicación.
.venv/Scripts/python.exe -m pytest -q
node --test tests/*.test.cjs
```

La suite exige esa separación, aplica migraciones y limpia únicamente datos de pruebas. Las pruebas de migración crean esquemas aislados dentro de la base de pruebas. Se verifican servicios obligatorios, categorías, carpetas únicas, reclasificación y versiones, catálogo protegido, permisos, CSRF, filtros inclusivos y por superposición, fechas independientes, Excel tipado y seguro, impresión, nombres de hojas y conservación de datos. El archivo de muestra generado para revisión utiliza exclusivamente datos ficticios de `_test` y permanece en `.runtime`, fuera del paquete entregado.

Se aprobaron **159 pruebas Python contra PostgreSQL real** y **26 pruebas JavaScript**. Se creó el respaldo real **postgres_antes_actualizacion7_20261021_154014.dump** antes de migrar. Después se compararon todas las columnas originales de usuarios, justificativos, reposos, cambios, sus detalles, vacaciones y comisionados: conservadas. `flask db check` y `pip check` finalizaron sin diferencias ni incompatibilidades. La comprobación HTTP validó login, todos los módulos, selectores con 14 servicios activos, carpetas, configuración, descarga de 14 hojas sin movimientos, auditoría y cierre de sesión, sin crear registros ficticios en la base real.

La hoja principal de la muestra pudo abrirse en Microsoft Excel. La revisión visual se interrumpió por Escape antes de revisar todas las hojas; no se realizó una impresión física.

## Archivos entregados

`entregables/fuentes_actualizacion7.zip` contiene las fuentes completas, las migraciones previas y nueva, plantillas, estilos, scripts, dependencias y pruebas. `entregables/ARCHIVOS_ACTUALIZACION_7.md` identifica los archivos nuevos y modificados. No incluye `.env`, contraseñas PostgreSQL, base local, respaldos, muestras de salud ni registros históricos del Excel.

La implementación nueva se concentra en `app/hospital_services/`, `app/models/hospital_services.py`, `app/templates/hospital_services/`, `app/static/js/service_selection.js`, `app/static/css/hospital_services.css` y la migración `0006_servicios_e_informes`. Los módulos anteriores solo incorporan su relación y selector de servicio, confirmación y trazabilidad de reclasificación.
