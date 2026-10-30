# Actualización 9 — Fotografías y documentos adjuntos

Integra adjuntos opcionales en Justificativo, Reposo, Cambio de Guardia normal y pagada, Vacaciones y Comisionados. Conserva las rutas, reglas, permisos, servicios, informes y registros anteriores. No importa datos del Excel de referencia ni modifica su disposición principal.

## Instalación y migración en Windows

1. Detén el servidor con Ctrl+C en su consola. Conserva `.env` y `instance/`: contienen la configuración privada y los archivos locales persistentes.
2. Actualiza las dependencias y ejecuta la migración con respaldo automático:

```powershell
Set-Location 'C:\Users\vi852\Desktop\Sistema de carga de documentos'
& .runtime/python/python.exe -s -m pip install -r requirements.txt
& .runtime/python/python.exe -s -m scripts.migrar_actualizacion9
& .runtime/python/python.exe -s -m flask --app run db check
```

También puedes usar `python.exe` de tu `.venv`. No ejecutes `create_all`, `drop_all`, reinicializaciones ni restauraciones sobre la base de uso. El script exige la revisión anterior, crea y verifica un `pg_dump` privado y compara todas las columnas anteriores, incluidos hashes, cuentas y auditorías. La revisión nueva es `0008_documentos_adjuntos`; una segunda ejecución conserva los datos. `scripts.initialize` e `iniciar.ps1` reconocen la transición y utilizan el mismo respaldo.

3. Para este equipo no necesitas un bucket. Los valores predeterminados guardan objetos privados en `instance/documentos_privados/`, fuera de `static`, excluidos de Git. Esa carpeta permanece después de cerrar sesión, reiniciar o actualizar archivos de código. **No borres ni reemplaces `instance/` al actualizar.** Restringe la carpeta mediante permisos de Windows a la cuenta del servidor y a los administradores de respaldo. Usa cifrado de disco y copias protegidas según la política institucional.
4. Inicia con `iniciar.ps1` o:

```powershell
& .runtime/python/python.exe -s -m waitress --listen=127.0.0.1:5000 run:app
```

## Configuración de almacenamiento y límites

`.env.example` enumera todas las opciones. Las fotografías son opcionales. Valores iniciales:

```dotenv
DOCUMENT_STORAGE_BACKEND=local
DOCUMENT_LOCAL_ROOT=
DOCUMENT_LOCAL_PERSISTENT=false
DOCUMENT_MAX_BYTES=8388608
DOCUMENT_MAX_FILES=5
DOCUMENT_MAX_PIXELS=40000000
DOCUMENT_PREVIEW_EDGE=2400
```

El límite de cantidad considera las fotografías **activas** del registro, incluidas cargas anteriores y concurrentes. Los retirados se conservan y dejan de consumir esa capacidad. El tamaño se verifica leyendo como máximo el límite más un byte. También se limita la resolución de entrada para evitar imágenes de descompresión excesiva. Ajusta resolución y concurrencia según la memoria disponible del servidor.

Los formularios de carga admiten peticiones multipart hasta `cantidad × tamaño + 2 MB`; login y otras operaciones conservan sus límites anteriores. Configura el proxy de producción para admitir hasta 42 MB con los valores iniciales. El máximo se aplica también en Flask; una petición excesiva recibe 413.

### S3, AWS, R2 u otro proveedor compatible

El usuario indicó que todavía no dispone de bucket. La integración está implementada y probada con el stub oficial de botocore; no hay una conexión real a un proveedor contratado ni se creó un bucket externo.

Antes del despliegue, crea un bucket **privado**, bloquea acceso público y páginas web, habilita cifrado en reposo y versionado/respaldos cuando el proveedor lo permita. Usa una credencial exclusiva del servidor, limitada a ese bucket y al prefijo `documentos/`, con `PutObject`, `GetObject`, `DeleteObject` y listado del prefijo para conciliación. No configures borrado automático por antigüedad para objetos documentales registrados o retirados. Guarda las claves solamente en variables secretas del proveedor o `.env`, nunca en Git ni en el chat.

```dotenv
DOCUMENT_STORAGE_BACKEND=s3
DOCUMENT_S3_BUCKET=nombre-del-bucket-privado
DOCUMENT_S3_ENDPOINT=https://endpoint-del-proveedor
DOCUMENT_S3_REGION=us-east-1
DOCUMENT_S3_ACCESS_KEY=
DOCUMENT_S3_SECRET_KEY=
DOCUMENT_S3_SSE=AES256
```

En AWS el endpoint puede quedar vacío; admite también credenciales del rol de ejecución mediante la cadena estándar de boto3. En R2/proveedores que no acepten `ServerSideEncryption`, deja `DOCUMENT_S3_SSE=` y utiliza el cifrado en reposo del proveedor. Nunca se solicita ACL pública, se generan URLs públicas o se entrega la URL del proveedor al navegador. Las vistas y descargas pasan por Flask y su autorización en cada petición.

**Railway:** el disco efímero no sirve como destino definitivo. Usa S3 o monta un volumen privado, configura `DOCUMENT_LOCAL_ROOT` con la ruta del volumen y declara `DOCUMENT_LOCAL_PERSISTENT=true`. Con `APP_ENV=production`, el servidor rechaza el backend local sin esa configuración explícita. Mantén HTTPS y las cookies seguras existentes.

Cambiar el backend no mueve los archivos anteriores. Cada fila conserva su backend de origen y rechaza lecturas desde un destino distinto. Antes de migrar de local a S3, respalda ambos componentes y realiza una migración controlada que copie originales/vistas conservando claves y SHA-256, verifique todos los objetos y actualice las referencias con una migración autorizada de PostgreSQL. No cambies simplemente `.env` ni borres el almacenamiento anterior. Esa transferencia deberá revisarse cuando se configure el bucket real.

## Uso y permisos

1. Abre cualquiera de los seis formularios. Al final aparece **DOCUMENTOS ADJUNTOS**.
2. Selecciona una o varias fotografías, agrega más o quita elementos antes de guardar. En equipos táctiles compatibles se muestra **TOMAR FOTO**, que solicita la cámara mediante el selector nativo del dispositivo; depende del navegador y sus permisos.
3. Selecciona el servicio y guarda. El diálogo de servicio conserva los archivos seleccionados. Sin JavaScript sigue disponible el selector múltiple y la validación en el servidor.
4. Los límites y el formato real se comprueban en Python con Pillow: JPG/JPEG, PNG y WEBP estáticos. Se rechazan imágenes dañadas, ejecutables, SVG, animaciones, extensiones engañosas, repeticiones y HEIC. No se ha instalado un conversor HEIC; conviértelo a un formato admitido antes de cargarlo.
5. Se conservan los bytes originales y una vista JPEG regenerada de hasta 2400 píxeles por lado, orientada y sin EXIF/GPS/comentarios. La vista permite leer y ampliar el documento; la descarga autorizada entrega el original con nombre genérico. No se realiza OCR ni se declara un análisis antivirus.

| Rol | Adjuntar al crear | Galerías históricas | Agregar a registros guardados | Descargar / retirar |
|---|---|---|---|---|
| Superadministrador | Sí | Sí | Sí | Sí |
| Jefatura | Sí | Sí | Sí | Sí |
| Operador | Sí | No | No | No |
| Supervisor | Sí | No | No | No |

Las restricciones se aplican en Python y a las URLs de imágenes. Reposos exige también permiso de diagnóstico. Los usuarios de carga reciben la confirmación y código del registro, sin galería histórica. Ningún documento es público. Los registros eliminados lógicamente no admiten carga ni consulta documental habitual; al restaurar el registro se conservan sus adjuntos activos.

Superadministrador/Jefatura pueden abrir **VER DOCUMENTOS ADJUNTOS** desde las tablas y carpetas por servicio, incluso cuando el contador es cero, y agregar fotos a registros antiguos. La galería incluye miniaturas, ampliación, zoom, navegación, fecha y responsable. Retirar exige una pantalla de confirmación y motivo; conserva originales e historial. Para sustituir, retira la copia anterior indicando el motivo y agrega la nueva.

## Integridad y fallos

`documentos_adjuntos` incluye claves foráneas reales para los cinco modelos principales; normal/pagada se distinguen por categoría. Un CHECK exige un único propietario y coincidencia con `tipo_modulo` y `registro_id`. Triggers impiden reasignar un documento, alterar su contenido/metadata original y mezclar la categoría de guardias. Las relaciones con usuarios usan RESTRICT.

El registro, los detalles, la metadata documental y la auditoría se confirman en una transacción PostgreSQL. Los objetos privados se escriben con identificadores aleatorios; si falla una carga se revierte PostgreSQL y se compensa el almacenamiento. El mismo envío no duplica adjuntos. Un bloqueo del registro serializa las cargas concurrentes para respetar el límite total.

PostgreSQL y S3 no ofrecen una transacción distribuida común: un corte abrupto puede dejar un objeto sin referencia. Ante un resultado de commit incierto se comprueba PostgreSQL desde otra conexión antes de retirar un objeto; si no se puede comprobar, se conserva para conciliación. Nunca se borra un archivo que tenga referencia, incluidos documentos retirados. Después de un error vuelve a seleccionar las imágenes; consulta el registro si se perdió la respuesta antes de reenviar.

```powershell
# Solo inspecciona; --verificar comprueba también SHA-256 de originales/vistas.
& .runtime/python/python.exe -s -m flask --app run conciliar-documentos --verificar
# Limpieza explícita: únicamente objetos sin referencia con más de 24 horas.
& .runtime/python/python.exe -s -m flask --app run conciliar-documentos --limpiar-huerfanos --verificar
```

La conciliación se coordina con las cargas mediante un bloqueo asesor PostgreSQL; no trata archivos en curso como huérfanos. Puede bloquear temporalmente cargas mientras recorre el almacenamiento. Programa la verificación fuera del horario de mayor uso. Si hay objetos faltantes/alterados, informa error para recuperar desde un respaldo; no inventa datos ni borra filas.

## Respaldo y recuperación

No basta con respaldar únicamente PostgreSQL ni únicamente el bucket. Detén el servidor, verifica el espacio disponible y ejecuta:

```powershell
& .runtime/python/python.exe -s -m scripts.respaldar_documentos
```

El respaldo privado en `.runtime/backups/documentos_FECHA/` contiene `postgres.dump`, `objetos/documentos/...` y `manifest.json` con SHA-256. Incluye originales y vistas de documentos activos **y retirados**, verifica cada copia y el catálogo de `pg_restore`; el manifiesto solo aparece al completar el proceso. No imprime credenciales, nombres ni diagnósticos. Se excluye de las entregas y de Git. Mantén una copia cifrada fuera del servidor/bucket y prueba periódicamente la recuperación en una base aislada y otro almacenamiento privado.

Para recuperar: verifica el manifiesto y el dump, restaura PostgreSQL en una base nueva vacía, repone los objetos con sus mismas claves en el mismo tipo de backend, configura la aplicación de prueba y ejecuta `conciliar-documentos --verificar`. Comprueba galerías y permisos antes de cambiar el tráfico. Nunca restaures por encima de la base de uso sin un procedimiento institucional aprobado. La cuenta y protección de `victor` se conservan en el dump; las claves de S3 se recuperan desde el gestor de secretos, no desde Git.

## Informes y auditoría

El Excel mantiene los tres bloques originales. Las hojas complementarias agregan **DOCUMENTOS ADJUNTOS** (Sí/No) y **Cantidad de fotografías** activas. No incorpora fotografías, nombres originales de archivos, rutas privadas ni enlaces al almacenamiento. Las consultas continúan usando el servicio y las fechas administrativas de cada módulo.

El historial administrativo registra cargas, retiros con motivo y descargas con actor, fecha, módulo, ID del registro e ID del documento. Ningún evento guarda bytes de imágenes ni secretos.

## Pruebas manuales

1. Con Superadministrador crea un reposo con una foto, un justificativo con tres y guardias normal/pagada con fotos. Verifica las carpetas por servicio y que cada galería corresponda al ID correcto.
2. Antes de guardar, añade y quita fotos; abre el diálogo de servicio y comprueba que la selección se conserve. Cancélalo: no debe guardarse nada.
3. Prueba cinco fotos, una sexta, un archivo superior a 8 MB, una extensión falsa, SVG, HEIC y una imagen dañada. Los errores no deben crear registros parciales ni adjuntos visibles.
4. Abre un registro antiguo sin adjuntos y agrega una imagen. Sus datos y fecha de modificación administrativa deben permanecer iguales. Retira con motivo y verifica el historial; agrega la sustitución.
5. Con Jefatura descarga un original. Con Operador/Supervisor carga un registro y prueba las mismas URLs de galería, vista, descarga y retiro: deben devolver 403. Sin sesión deben redirigir al login.
6. Sustituye el ID de registro/módulo en una URL de imagen: debe devolver 404, sin mostrar documentos de otro registro. Los nombres de objetos no incluyen datos del funcionario.
7. Cierra sesión y reinicia el servidor conservando `instance/` o el bucket/volumen. Verifica las imágenes y el contador de Excel.
8. Simula una indisponibilidad de almacenamiento en pruebas: no debe confirmarse una operación incompleta. Ejecuta la conciliación y prueba un respaldo/recuperación aislados.

## Pruebas automatizadas y entrega

Usa exclusivamente `TEST_DATABASE_URL` de una base dedicada terminada en `_test`:

```powershell
& .runtime/python/python.exe -s -m pytest -q
node --test tests/*.test.cjs
```

Las pruebas documentales usan un almacenamiento privado de pruebas separado; nunca escriben fotografías ficticias en la base de uso. El paquete `entregables/fuentes_actualizacion9.zip` y el inventario `entregables/ARCHIVOS_ACTUALIZACION_9.md` incluyen código, migración, plantillas y pruebas; excluyen `.env`, archivos privados, respaldos y datos de prueba.

Validación final local del 22/10/2026: **267 pruebas Python y 31 JavaScript aprobadas**. Migración real aplicada con respaldo verificado y comparación de datos anteriores; `flask db check`, `pip check`, conciliación, respaldo conjunto y prueba HTTP del servidor aprobados. Consulta `VALIDACION.md` para el alcance y las limitaciones: S3 sin bucket real y cámara/interfaz sin revisión visual en un dispositivo físico.
