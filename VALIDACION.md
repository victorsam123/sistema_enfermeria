# Validación de la primera etapa

Realizada el 21 de octubre de 2026 con Python 3.13.9 y PostgreSQL 18.

- 16 pruebas de integración aprobadas contra la base independiente `enfermeria_test`.
- Login real mediante HTTP y redirección al Dashboard comprobados con `victor`.
- Estado PostgreSQL comprobado desde el Dashboard; no se utiliza una conexión simulada.
- CSS Bootstrap, Bootstrap Icons, fuente de iconos, estilos y JavaScript locales respondieron HTTP 200.
- Cierre de sesión mediante POST con CSRF y posterior rechazo del acceso directo comprobados.
- Inicialización repetida con la cuenta existente: conserva su ID y contraseña; también se verificó al retirar la variable de contraseña inicial.
- Hash scrypt, estado activo y protección de la cuenta inicial comprobados.
- Pruebas de bloqueo de DELETE, UPDATE de estado/protección/identidad/rol y TRUNCATE ejecutadas en PostgreSQL.
- Dependencias del entorno aislado verificadas con `pip check`.

La revisión visual mediante navegador no pudo realizarse porque no hay un navegador conectado disponible en esta sesión. El diseño responsive y los controles de mostrar contraseña/menú móvil están implementados; conviene revisarlos visualmente en los dispositivos de destino.

La base utilizada por la aplicación local se guarda en `.runtime/pgdata` y es independiente del servicio PostgreSQL previamente instalado. El despliegue externo en Railway no se realizó; las instrucciones y configuración están en README.md.

## Actualización 2: Dashboard

- 19 pruebas de integración Python aprobadas contra `enfermeria_test`, incluyendo los casos anteriores de autenticación y protección.
- 2 pruebas JavaScript aprobadas con el ejecutor integrado de Node.js: reloj independiente de la hora/zona del dispositivo, cambio de fecha a medianoche y apertura del aviso para los cinco módulos.
- La cuenta `victor` de la base de la aplicación se consultó antes y después de la validación: se conservaron ID, username, hash de contraseña, rol, estado, protección y fecha de creación.
- Se añadió únicamente un endpoint de lectura protegido, `/api/reloj`, además del contenido del Dashboard. No se ejecutaron migraciones ni inicialización en la base de la aplicación.
- El reloj usa `zoneinfo('America/Asuncion')` del servidor y avance monotónico en el navegador, con actualización visual cada segundo y sincronización cada minuto.
- Tras reiniciar únicamente Waitress, se verificaron por HTTP el login, el Dashboard con cinco tarjetas, `/api/reloj`, los recursos estáticos y el cierre de sesión. `pip check` no detectó dependencias incompatibles.
- La consulta de superficies disponibles volvió a devolver cero navegadores conectados; la revisión visual permanece pendiente.

## Actualización 3: registros administrativos

- 48 pruebas Python aprobadas contra PostgreSQL de pruebas: autenticación y protecciones previas, nuevas rutas restringidas, CSRF, creación, filtros, edición autorizada con control de versiones, errores conservando datos del formulario, turnos nocturnos y separación NORMAL/PAGADA.
- Se verificó que dos envíos concurrentes con la misma clave crean exactamente una fila y que un formulario nuevo permite una carga legítima con datos iguales.
- 5 pruebas JavaScript aprobadas: reloj y avisos existentes, calendario DD/MM/AAAA, fechas imposibles, validación de participantes/horario y prevención de doble clic.
- Se aplicó `0002_administrative_records` después de crear un respaldo PostgreSQL en `.runtime/backups`. La migración añadió únicamente las dos tablas y sus índices/restricciones.
- Se compararon todas las cuentas antes y después, conservando sus campos y hashes; también se compararon los triggers existentes de protección de usuarios. Se conservaron los registros anteriores.
- `flask db check` no detectó operaciones pendientes; `pip check` no detectó dependencias incompatibles.
- Se verificaron por HTTP las nuevas pantallas, formularios, recursos y navegación, junto con el login, reloj y logout. No se cargaron registros de ejemplo en la base de la aplicación.
- En la entrega inicial las fotos no estaban disponibles y el usuario autorizó seguir la estructura textual. No se asignó significado a G o L.

### Adaptación posterior a las fotos 1 y 2

- Ambas referencias se recibieron y revisaron. Las tablas incorporan una celda agrupada por solicitante dentro de cada página, pares de líneas S/R, columna de identificación y horario compartido por registro, con la identidad visual oscura institucional.
- Se verificó el HTML de tres registros en distintas fechas, dos solicitantes agrupados, seis líneas S/R y el horario correspondiente a cada par, sin escribir registros en la base de la aplicación.
- Se volvió a ejecutar la prueba de categorías separadas y turnos nocturnos: aprobada. No se modificaron formularios, campos, categorías ni esquema de base de datos. G y L siguen sin interpretación.

## Actualización 4: Comisionados y Vacaciones

- 82 pruebas Python aprobadas contra PostgreSQL de pruebas, incluidas todas las anteriores. Cubren creación y edición, responsable y fechas de carga, total inclusivo, un solo día, año bisiesto, fines de semana, cambio de año, manipulación del total recibido, fechas invertidas, restricciones PostgreSQL, filtros, orden, doble envío, conflictos de edición, CSRF, permisos y persistencia tras logout y recreación de la aplicación.
- 12 pruebas JavaScript aprobadas. El cálculo de vacaciones se probó junto con los selectores de fecha existentes: cambio desde calendario, actualización automática, rechazo del término anterior y fechas imposibles.
- Se respaldó PostgreSQL en `.runtime/backups/` antes de aplicar `0003_comisionados_vacaciones`. Se verificaron después las cuentas, contraseñas, triggers y todos los registros previos de Justificativos y Cambios de Guardia, conservados íntegramente.
- `flask db check` y `pip check` finalizaron sin diferencias ni incompatibilidades.
- Comprobación HTTP satisfactoria: login, cinco accesos, seis pantallas administrativas, formularios, recursos, reloj y logout. No se guardaron registros de ejemplo en la base de la aplicación.
- Reposo conserva sus funciones anteriores. Solo se reservó un paquete para implementar su registro después de recibir la foto 3; no se definieron campos ni tabla de reposos.

## Actualización 5: Reposo según foto 3

- Se encontró y revisó `foto 3.png`. La tabla conserva sus seis columnas y añade únicamente la acción de edición y la auditoría. No se importaron los datos de la imagen.
- 105 pruebas Python aprobadas contra PostgreSQL de pruebas y 19 pruebas JavaScript aprobadas, incluyendo las regresiones anteriores. Se verificaron 2 y 14 días, fechas iguales, año bisiesto, cambio de año, total adulterado, campos y entrega obligatorios, fechas invertidas/imposibles, edición, conflictos de versión, búsqueda, filtros, cuatro órdenes, paginación, reenvío, permisos, CSRF y persistencia después de logout y recreación de la aplicación.
- Se creó un respaldo PostgreSQL antes de aplicar `0004_reposos`. La migración añadió únicamente `reposos` con sus índices y restricciones. Se compararon las cuentas, contraseñas, triggers y todos los registros de las cuatro tablas de módulos anteriores: conservados.
- `flask db check` no detectó migraciones pendientes y `pip check` no detectó incompatibilidades.
- Comprobación HTTP satisfactoria de Reposo y sus campos/ordenamientos, accesos anteriores, módulos, recursos, reloj y logout. No se guardaron registros de ejemplo en la base de la aplicación.
- La consulta de superficies disponibles no encontró navegador conectado. La revisión visual permanece pendiente.

## Actualización 6: correcciones de navegación y fechas

- Se revisó la foto 4 y se adaptaron las tablas para agrupar por ID de operación, sin mezclar cambios independientes con los mismos nombres. No se asignó significado a G o L.
- 127 pruebas Python aprobadas contra PostgreSQL real, incluidas las regresiones anteriores. Se repitieron las 22 pruebas específicas tras la última revisión.
- Se verificaron fechas 04/10 y 05/10 con horarios distintos, 02/10, 08/10 y 17/10 como fechas individuales, 120 filas en una operación, edición con fechas adicionales, conservación de IDs y creador, conflictos de versión, códigos, categorías, duplicados y envíos concurrentes.
- Una prueba de migración creó registros con el esquema anterior en un esquema aislado de la base de pruebas, ejecutó la actualización y confirmó fechas, horarios, categorías y coberturas conservados.
- Cobertura opcional verificada en HTML, creación y edición: ausencia almacenada como NULL y mostrada como SIN COBERTURA; una cobertura válida se conserva como fecha. Los valores no vacíos e inválidos se rechazan.
- 22 pruebas JavaScript aprobadas, incluyendo filas adicionales con identificadores únicos, eliminación de borradores, validación de fechas/horarios, nombres y detección de duplicados.
- Se creó un respaldo PostgreSQL antes de aplicar `0005_guardias_fechas_y_cobertura`. Se compararon todas las columnas originales de las tablas de módulos, cuentas, hashes y triggers del administrador: conservados. Las columnas antiguas de guardias permanecen.
- `flask db check` y `pip check` finalizaron sin diferencias pendientes ni incompatibilidades.
- HTTP verificado: regreso al panel principal, formulario de guardias con fechas independientes, cobertura opcional, módulos anteriores, recursos, reloj y logout. No se cargaron registros ficticios en la base de la aplicación.
- No se encontró navegador conectado para la revisión visual.

## Actualización 7: servicios, carpetas e informes

- 159 pruebas Python aprobadas en PostgreSQL real y 26 pruebas JavaScript aprobadas. Se repitió la suite completa con la versión final.
- Catálogo inicial de 14 servicios, más categoría pendiente para cargas anteriores. Se verificaron inicialización idempotente, FKs reales, obligatoriedad en los seis formularios, rechazo de servicios inexistentes, pendientes e inactivos y conservación tras crear otra instancia.
- Carpetas virtuales sin duplicar registros: conteos, separación de servicio/categoría, navegación y edición. Reclasificación desde una acción específica y desde la edición normal, con historial anterior/nuevo y control de versiones.
- Configuración: alta sin duplicar códigos, cambio de nombre sin perder datos, desactivación y consulta histórica. PostgreSQL impide DELETE/TRUNCATE del catálogo y cambios de sus códigos permanentes.
- Exportación individual, por categoría y de todos los servicios; sin movimientos, sin Hoja1, sin mezcla entre UTI-P y Urgencia Trauma. Se verificaron límites inclusivos, superposición de períodos, total original, fechas independientes de guardia, participantes, códigos literales y categoría pagada separada.
- El XLSX se inspeccionó como archivo OOXML: integridad ZIP, fechas numéricas y formatos, literales que no se convierten en fórmulas ni enlaces, nombres únicos de hasta 31 caracteres, tres bloques principales, hojas complementarias, A4 horizontal, ajuste al ancho, áreas y títulos de impresión. La vista previa y la descarga mantienen los mismos criterios de consulta.
- Todas las rutas nuevas exigen autenticación y rol autorizado. Se probaron CSRF, denegación de acceso a diagnósticos para otros roles, registros de generación/descarga y límite explícito de filas sin truncamiento silencioso.
- Antes de migrar se verificó el respaldo `.runtime/backups/postgres_antes_actualizacion7_20261021_154014.dump`. Tras migrar se compararon todas las columnas anteriores de usuarios y las seis tablas de registros/detalles, incluidos hashes y triggers del administrador: conservadas.
- `flask db check` no detectó operaciones pendientes y `pip check` no detectó incompatibilidades.
- HTTP del servidor real: login, módulos anteriores, 14 opciones activas, carpetas, configuración, reloj, descarga privada de un informe de 14 hojas sin movimientos, auditoría y logout. No se guardaron datos ficticios en la base de uso.
- Se abrió la muestra con datos ficticios en Microsoft Excel y se revisó su hoja principal. El usuario interrumpió el control de aplicaciones con Escape; no se completó la revisión visual de todas las hojas ni se imprimió físicamente. El archivo de referencia no se modificó ni se importaron sus filas.
- Se comprobaron byte por byte los componentes de autenticación, usuarios, configuración y rutas principales frente a la entrega anterior. El ZIP completo excluye credenciales, respaldos y muestras de datos.

## Actualización 8: usuarios, roles y permisos

- 219 pruebas Python y 28 JavaScript aprobadas antes de incorporar adjuntos. Cuatro roles, formularios de carga, cuentas privilegiadas, primer acceso, revocación de sesiones, auditoría, eliminación lógica y restauración verificados.
- Respaldo previo `.runtime/backups/postgres_antes_actualizacion8_20261021_163016.dump`; revisión `0007_usuarios_roles_eliminacion` aplicada conservando hashes, identidad, estados, registros, servicios y protecciones. Inicialización repetida sin restablecer la contraseña.
- La prueba HTTP detectó y corrigió los valores iniciales de filtros vacíos de Gestión de Usuarios. Se verificaron nuevamente acceso, cuatro roles, módulos, historial y rechazo de acciones sobre victor. No se crearon cuentas ficticias en la base de uso.
- `flask db check` y `pip check` aprobados. Fuentes conservadas en `entregables/fuentes_actualizacion8.zip`.

## Actualización 9: documentos privados

- Regresión completa final: **267 pruebas Python aprobadas** en PostgreSQL real (218,89 segundos). Incluye 48 pruebas documentales con S3 mediante Stubber oficial de botocore, concurrencia, respaldo real de la base de pruebas y comparación SHA-256 de archivos. **31 pruebas JavaScript aprobadas**.
- Cada uno de los seis formularios fue probado con tres imágenes reales (PNG, JPEG y WEBP) y los cuatro roles. Se comprobaron las asociaciones en PostgreSQL, usuarios responsables, auditoría, originales recuperables y vistas regeneradas.
- Se verificaron formatos falsos, ejecutables, SVG, HEIC no soportado, imágenes dañadas/animadas, tamaño y cantidad excesivos, duplicados, falta de servicio y CSRF. Las cargas rechazadas no crearon registros ni archivos visibles.
- Fallos simulados después de PUT y durante commit revirtieron registros/metadata y compensaron objetos. Cargas concurrentes respetaron el total máximo de cinco fotografías activas. Los reenvíos del mismo lote no duplicaron documentos.
- Integridad SQL: FKs reales, un único propietario, prohibición de reasignación y categoría normal/pagada protegida. Accesos cruzados entre módulos/IDs devolvieron 404; Operador/Supervisor recibieron 403 y sin sesión se redirigió al login.
- Agregar a registros antiguos conservó sus datos, versión, creador y fecha de modificación administrativa. Retirar conservó los objetos y registró actor, fecha y motivo. Un registro eliminado ocultó sus documentos; restaurarlo recuperó las vistas activas. Una instancia nueva leyó originales/vistas del almacenamiento persistente de pruebas.
- Carpetas mostraron vínculos y conteos correctos. Se inspeccionó OOXML para verificar indicadores Sí/No y cantidad en complementos, ausencia de imágenes embebidas y conservación de los bloques A:E, G:I y K:P.
- Respaldo previo de uso: `.runtime/backups/postgres_antes_actualizacion9_20261022_205159.dump`. Revisión `0008_documentos_adjuntos` aplicada, comparando todas las columnas anteriores e historiales. Usuarios, hashes, servicios y registros conservados; inicialización repetida sin restablecimientos.
- Respaldo conjunto de uso: `.runtime/backups/documentos_20261022_205259_603744/`, con dump verificado y manifiesto. La base de uso no tenía fotografías; la prueba aislada respaldó originales y vistas, incluidos documentos retirados, y verificó cada SHA-256. La conciliación real no encontró faltantes ni huérfanos.
- HTTP real: login existente, Gestión de Usuarios, módulos, seis formularios multipart con adjuntos, recursos CSS/JS, control de sesión y fotografías privadas. No se agregaron registros ni fotografías ficticias a la base de uso. `flask db check` no detectó diferencias y `pip check` no detectó incompatibilidades.
- Almacenamiento local privado configurado por defecto fuera de static y Git. No hay bucket ni credenciales S3 del usuario; la conexión externa permanece pendiente. No se declara una prueba con un proveedor contratado ni una revisión visual en navegador/cámara física.

## Actualización 10: funcionarios y fichas personales

- Regresión final: **323 pruebas Python aprobadas** en PostgreSQL real (215,29 segundos) y **33 pruebas JavaScript aprobadas**. Incluye 56 pruebas específicas de funcionarios; las anteriores siguen aprobadas.
- Alta, ficha completa, búsqueda exacta con/sin puntos y ceros iniciales, rechazo de duplicados y reenvíos idempotentes. Cédulas inválidas, campos vacíos, fechas inválidas/futuras/incompletas, ingreso anterior al nacimiento, vínculos negativos/decimales y servicios inexistentes fueron rechazados sin crear fichas parciales.
- Edad y antigüedad probadas con los ejemplos solicitados, cumpleaños pendientes, meses de distinta duración y años bisiestos. No existen columnas que congelen edad, antigüedad o año de ingreso. Solo se admite fecha completa para antigüedad exacta.
- Superadministrador y Jefatura administraron fichas en pruebas. Operador/Supervisor recibieron 403 en buscador general, fichas, edición, historial y fotografía; el Dashboard no expuso el módulo para esos roles. Sus búsquedas operativas entregaron exclusivamente ID y nombre, con respuestas no cacheables.
- API operativa: POST, CSRF y contexto firmado de formulario/sesión. Tokens falsos y de otra sesión fueron rechazados; la respuesta de límite fue 429. No hay búsqueda por cédula en GET ni endpoint de listado general para roles de carga.
- Vínculos explícitos verificados desde los seis formularios. Se rechazaron IDs inexistentes y nombres que no corresponden a la ficha. Cambiar el nombre de una ficha no alteró textos históricos. La migración dejó NULL las relaciones previas, sin coincidencias automáticas por nombre.
- Fotografías reales de prueba: asociación individual, vista privada, sustitución con retiro/auditoría, retención de originales y lectura desde una instancia nueva. Imágenes falsas, HEIC y múltiples fotos personales fueron rechazadas. Ante falla del almacenamiento se conservó la fotografía anterior y se compensaron objetos nuevos.
- PostgreSQL rechazó reasignar la foto de otra ficha, cédulas no canónicas, vínculos negativos y fechas futuras mediante SQL. Un índice parcial limita a una foto activa por funcionario; FK y triggers diferidos verifican la referencia final. Ediciones obsoletas devolvieron 409 y el creador original se conservó.
- Se verificaron historial de campos modificados sin replicar domicilio/cédula/nacimiento en descripciones, actualización autorizada de dirección y conservación de un servicio inactivo al corregir otros datos.
- Respaldo conjunto real previo: `.runtime/backups/antes_actualizacion10_20261022_213731_543703/`, con `postgres.dump` y manifiesto verificados. Revisión `0009_funcionarios` aplicada con comparación de todas las columnas históricas, documentos, cuentas, hashes, servicios e historiales, y de las protecciones previas. No se importaron funcionarios ni se modificó la contraseña de victor.
- `flask db check` no detectó diferencias, `pip check` no detectó incompatibilidades, la inicialización repetida conservó el administrador y la conciliación no encontró objetos faltantes ni huérfanos.
- HTTP real: login/logout, Dashboard con Funcionario, buscador POST sin coincidencias, formulario de alta precompletado sin guardar, seis búsquedas operativas, recursos CSS/JS y exigencia de sesión para fichas/fotografías. Se compararon las cantidades originales y la identidad/hash/protección de victor; no se crearon fichas ni registros ficticios en la base de uso.
- Se conserva el almacenamiento privado local/S3 de la actualización 9. No se configuró un bucket externo ni se probó una cámara física o una revisión visual en navegador. Las pruebas de fotografía y permisos se realizaron con imágenes reales en una base y almacenamiento aislados.

## Actualización 11: múltiples vínculos laborales

- Regresión final: **348 pruebas Python aprobadas** en PostgreSQL real (276,85 segundos) y **36 pruebas JavaScript aprobadas**. Incluye 28 pruebas nuevas de vínculos y 53 pruebas adaptadas de funcionarios. Se retiraron las tres validaciones del antiguo contador manual, ahora calculado y de solo lectura.
- Se verificaron tres vínculos dentro de una sola ficha, cédula y fotografía, numeración independiente por funcionario y más de tres vínculos. Las antigüedades coinciden con los tres ejemplos al 22/10/2026, utilizando relativedelta y la fecha de Paraguay.
- La edición cambió solamente el vínculo elegido y dejó fechas anterior/nueva, responsable e identificador en el historial. Desactivación, reactivación, motivos, confirmación y total activo cero fueron probados sin borrado físico.
- Reenvíos idempotentes, bloqueo concurrente de numeración, versiones obsoletas, intentos de manipular total/número/año/antigüedad, fechas futuras/incompletas/anteriores al nacimiento y ausencia de CSRF fueron comprobados. PostgreSQL rechazó la modificación manual del contador y DELETE/TRUNCATE de vínculos.
- Superadministrador y Jefatura administraron los vínculos en pruebas. Operadores y Supervisores recibieron 403 en GET/POST de alta, edición, estado, cálculo privado y expedientes. Los identificadores de vínculo de otra ficha fueron rechazados.
- Migración aislada con contadores históricos 0, 1 y 3: una fecha exacta produjo solamente vínculo 1 activo, se archivó el contador anterior y se conservaron las columnas originales. No se inventaron vínculos adicionales; ejecutar nuevamente no duplicó filas. La política para el antiguo cero está documentada en ACTUALIZACION_11.md.
- Los seis apartados del expediente mostraron exclusivamente registros relacionados mediante ID, con sus galerías y documentos existentes. No hubo asociaciones por coincidencia de nombres. Referencias futuras de documento a dos vínculos reutilizaron un único archivo; PostgreSQL rechazó asociaciones con otra persona.
- Una instancia nueva recuperó ficha, fotografía y vínculos desde PostgreSQL y almacenamiento persistente. No se añadieron campos de edad o antigüedad congelados ni copias de fotografías por vínculo.
- Respaldo conjunto real previo: `.runtime/backups/antes_actualizacion11_20261022_221840_459343/`, con dump y manifiesto verificados. Revisión **0010_vinculos_laborales** aplicada conservando datos, documentos, servicios, cuentas, hashes, protección de victor e historiales. Se conservaron las referencias originales de ingreso y contador declarado.
- `flask db check`: sin operaciones pendientes; `pip check`: sin incompatibilidades. Inicialización repetida: administrador conservado. Conciliación real: 4 referencias y 4 objetos, sin faltantes, huérfanos ni fallos de integridad.
- HTTP real: login/logout, Dashboard, seis módulos y formularios con adjuntos, buscador de funcionarios, contador de vínculos readonly, fecha inicial, nuevos CSS/JS, rutas inexistentes y exigencia de sesión. Se compararon cantidades originales e identidad/hash/protección de victor; no se crearon fichas ni vínculos ficticios en la base de uso.
- El paquete se comparó byte por byte con la entrega 10: autenticación, usuario protegido, configuración, Dashboard y módulos administrativos ajenos a esta actualización permanecen idénticos. No hay archivos anteriores eliminados. El inventario enumera los cambios concretos.
- Se mantiene el almacenamiento privado existente. No se contrató/configuró un bucket externo ni se probó una cámara física. La interfaz se validó con pruebas de formularios, plantillas, JavaScript y HTTP; no se declara una revisión visual completa en navegador.
