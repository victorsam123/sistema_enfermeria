# Actualización 8 · Gestión de usuarios, roles, auditoría y eliminación lógica

Esta actualización amplía la aplicación existente, con el mismo login, Dashboard, servicios y módulos. No utiliza el Excel como fuente de registros ni cambia su catálogo de servicios. La cuenta principal `victor` conserva su contraseña, identidad, estado activo y protección permanente.

## Roles y funciones

Los roles se guardan como códigos estables en PostgreSQL. La interfaz muestra sus nombres institucionales:

| Función | SUPERADMIN | JEFATURA | OPERADOR | SUPERVISOR |
|---|:---:|:---:|:---:|:---:|
| Iniciar sesión y cargar en los seis formularios | Sí | Sí | Sí | Sí |
| Seleccionar un servicio activo | Sí | Sí | Sí | Sí |
| Consultar registros y diagnósticos guardados | Sí | Sí | No | No |
| Editar y reclasificar registros | Sí | Sí | No | No |
| Eliminar lógicamente con motivo y confirmación | Sí | Sí | No | No |
| Consultar y restaurar eliminados | Sí | No | No | No |
| Carpetas por servicio | Sí | Sí | No | No |
| Generar, descargar Excel e imprimir documentos | Sí | Sí | No | No |
| Gestionar cuentas de Operadores y Supervisores | Sí | Sí | No | No |
| Crear o modificar otras cuentas privilegiadas no protegidas | Sí | No | No | No |
| Configurar servicios hospitalarios | Sí | No | No | No |
| Cambiar su propia contraseña verificando la actual | Sí | Sí | Sí | Sí |

Nombres visibles: **Superadministrador**, **Jefatura de Enfermería**, **Operador** y **Supervisor**. Supervisor tiene su código y permisos independientes, aunque sus funciones iniciales coincidan con Operador.

La política está centralizada en `app/security/permissions.py`. Las rutas comprueban permisos antes de consultar, modificar, imprimir o exportar. Una operación prohibida devuelve **403** y **No tiene permisos para realizar esta operación**. Sin una sesión válida se conserva la redirección del login existente. Un POST sin CSRF válido devuelve 400.

Operadores y Supervisores pueden seleccionar cualquiera de los servicios activos para una carga, conforme a la selección ya existente. No se inventaron asignaciones de servicios por usuario: no pueden consultar carpetas ni registros históricos de ningún servicio. Si posteriormente se definen asignaciones individuales, la política se puede ampliar.

## Gestión de usuarios

El botón **Gestión de Usuarios** aparece en el Dashboard y menú únicamente para Superadministrador y Jefatura.

**+ AGREGAR NUEVO USUARIO** solicita nombre completo, username único, contraseña inicial, confirmación, rol y estado. Los usernames se normalizan a minúsculas; PostgreSQL impide duplicados incluso con distinta capitalización. Se aceptan de 3 a 80 caracteres: letras, números, punto, guion y guion bajo.

Las contraseñas nuevas requieren de 12 a 128 caracteres, mayúsculas, minúsculas y números. No pueden incluir el username ni comenzar o terminar con espacios. Se almacenan con scrypt de Werkzeug. Los formularios permiten mostrar u ocultar las contraseñas; estas no se vuelven a mostrar al informar un error ni aparecen en las tablas o el historial.

El rol inicial seleccionado por defecto es Operador. Superadministrador puede escoger los cuatro roles. Jefatura solo puede escoger Operador o Supervisor; un intento de enviar otro rol manualmente se rechaza en el backend. También se comprueba el rol actual de la cuenta destinataria bajo bloqueo al modificarla, para impedir operar sobre una cuenta que haya sido promovida mientras estaba abierto el formulario.

La tabla permite buscar por nombre o username, filtrar rol y estado, editar, restablecer contraseñas, activar/desactivar y consultar actividad. Jefatura ve y administra únicamente las cuentas de carga. No puede consultar la actividad de otras cuentas privilegiadas ni modificarlas mediante URLs directas.

No se incorporó borrado físico de cuentas. Desactivar conserva su autoría y todas sus relaciones con los registros.

## Primer acceso y sesiones

Todos usan `/login` con el diseño existente. Una cuenta nueva, incluso si recibe un rol privilegiado, debe cambiar su contraseña inicial en **Mi cuenta → Cambiar contraseña** antes de utilizar los módulos. La misma obligación se aplica después de un restablecimiento administrativo.

El cambio exige la contraseña actual y una nueva distinta, con confirmación. Se limita el número de intentos. Mientras está pendiente, las rutas de negocio redirigen al cambio obligatorio; no se permite guardar ni exportar mediante un POST directo. El reloj, los recursos estáticos y el cierre de sesión siguen disponibles.

Cambiar contraseña, username, rol, estado o la obligación de cambio modifica la versión de seguridad en PostgreSQL. La firma de sesión incorpora esa versión y el rol. Las sesiones anteriores dejan de ser válidas; reactivar una cuenta no revive una sesión antigua. Se bloquea también el caso en que se restablece una contraseña entre su verificación y la creación de la cookie.

Las sesiones previas a esta actualización deben iniciar sesión nuevamente por el nuevo formato de verificación. No se restablece ninguna contraseña existente. Las cuentas anteriores conservan su condición de primer acceso; la migración no obliga a `victor` a reemplazar su contraseña inicial.

## Cuenta principal protegida

`victor` conserva su mismo ID, username, hash, fecha de creación, estado activo y protección. Su rol se representa ahora con el código **SUPERADMIN**, manteniendo el rótulo Superadministrador.

La cuenta no admite eliminación, desactivación, cambio de identidad, pérdida de protección ni cambio de rol, tanto en Python como en PostgreSQL. La gestión de cuentas no ofrece esas acciones sobre cuentas protegidas y las rechaza desde cualquier otra cuenta, incluso otro Superadministrador.

El titular puede cambiar su contraseña desde el menú de perfil verificando la contraseña actual. Se conserva también el procedimiento local autorizado `flask --app run change-admin-password`, que registra la operación y revoca las sesiones anteriores. Ninguna migración invoca un restablecimiento de contraseña.

## Formularios según el rol

Se conservan las rutas de Justificativo, Reposo, Cambio de Guardia normal y pagada, Vacaciones y Comisionados, sus validaciones, fechas, códigos, selección de servicio e idempotencia de carga.

Superadministrador y Jefatura ven los formularios y sus consultas, edición, eliminación e impresión. Operadores y Supervisores solo ven la carga. Las consultas de historial ni siquiera se ejecutan al construir sus páginas; no se trata de ocultar datos ya enviados al navegador.

Después de una carga correcta, las cuentas de carga reciben únicamente la confirmación del servicio y el **código del registro**. El formulario se limpia mediante redirección y no se habilitan enlaces para editar, eliminar o ver historial.

Los accesos de Cambio de Guardia Pagada se conservan en la navegación y en Reposo.

## Eliminación lógica y restauración

Los registros de los cinco modelos principales incluyen `eliminado`, `usuario_eliminacion_id`, `fecha_eliminacion` y `motivo_eliminacion`. Los cambios normales y pagados comparten ese estado en su operación principal; sus detalles y códigos permanecen registrados.

**Eliminar** abre una pantalla de confirmación con el registro, su servicio y un motivo obligatorio. El POST confirma la intención, verifica la versión y guarda en una sola transacción quién eliminó, cuándo y por qué. PostgreSQL exige que los metadatos estén completos. No se ejecuta DELETE sobre registros administrativos desde las funciones del sistema.

Los eliminados se excluyen de las consultas habituales, filtros, carpetas, conteos, vistas previas, impresiones y exportaciones. Tampoco se pueden abrir mediante una URL de edición anterior. El creador y la fecha original permanecen intactos.

**Registros eliminados**, exclusivo del Superadministrador, permite filtrar por categoría, consultar el detalle original y restaurar. Restaurar vuelve a incluirlo en consultas e informes y deja un evento con los metadatos de la eliminación anterior. Los IDs, servicio, datos y detalles se conservan. Jefatura no accede a esta sección ni a su endpoint de restauración.

## Informes e impresión

Las funciones de informes existentes mantienen sus filtros y formato. Solo Superadministrador y Jefatura pueden generarlos, ver su vista previa o descargarlos; la autorización se verifica antes de crear el archivo. Los diagnósticos también se reservan a esos roles al consultar datos guardados.

Se agregó una vista de **Imprimir** por registro, protegida por los mismos permisos administrativos. Muestra encabezado institucional, servicio, ID, datos y autoría. Abre el diálogo de impresión solo al pulsar **IMPRIMIR DOCUMENTO**. No imprime automáticamente.

Los Excel descargados pueden imprimirse posteriormente desde Excel. Operadores y Supervisores no reciben enlaces de impresión/exportación ni acceden a sus endpoints. Sus formularios de carga tampoco se presentan como documentos administrativos en la hoja de estilos de impresión.

## Auditoría

`auditoria_usuarios` registra actor, cuenta afectada, acción, fecha/hora y descripción para altas, cambios de datos, roles, activaciones/desactivaciones, restablecimientos y cambios de contraseña. No contiene contraseñas, confirmaciones ni hashes.

Se amplía el historial administrativo existente para registrar creación, modificación, eliminación lógica, restauración, accesos, preparación de impresión, generación/vista previa/descarga de informes y administración de cuentas. Los eventos se guardan en la misma transacción que la operación correspondiente. Las cargas repetidas con la misma clave de envío no duplican el registro ni su evento de creación.

El historial de accesos `logs_acceso` se conserva. La actividad de una cuenta muestra sus eventos de cuentas, operaciones y accesos con paginación. Jefatura solo consulta actividad de cuentas que puede administrar y no ve eventos de cuentas privilegiadas en su historial de usuarios.

## Migración y ejecución en Windows

La nueva revisión es **0007_usuarios_roles_eliminacion**, posterior a `0006_servicios_e_informes`.

La migración amplía `usuarios`, crea `auditoria_usuarios` y añade eliminación lógica a las tablas existentes. Traduce los cuatro nombres de roles anteriores a códigos, conserva hashes y datos y crea un índice de username sin distinguir mayúsculas. Si aparecen roles anteriores desconocidos, se detiene sin asignar privilegios por suposición.

La traducción del rol protegido se realiza bajo bloqueo exclusivo y dentro del DDL transaccional de PostgreSQL. La barrera de actualización se vuelve a instalar antes de confirmar; otras conexiones no pueden escribir en ese intervalo. Una falla revierte también los cambios de esquema. Se conserva el bloqueo de TRUNCATE de usuarios.

En otra instalación de la revisión anterior, detén su servidor y ejecuta desde la carpeta del proyecto:

```powershell
& .runtime/python/python.exe -s -m pip install -r requirements.lock.txt
& .runtime/python/python.exe -s scripts/migrar_actualizacion8.py
& .runtime/python/python.exe -s -m flask --app run db check
& .runtime/python/python.exe -s -m waitress --listen=127.0.0.1:5000 run:app
```

En un entorno estándar, sustituye el ejecutable por `.venv/Scripts/python.exe`. No reemplaces `.env`, no recrees PostgreSQL ni ejecutes un initdb sobre sus datos.

`migrar_actualizacion8.py` requiere la revisión de la actualización 7 o la actual. Antes de migrar ejecuta pg_dump, verifica el respaldo con pg_restore y, después, compara las columnas anteriores de usuarios, servicios, historial y registros. La única traducción esperada de datos anteriores es el código del rol; los hashes y demás valores originales se conservan. Si falla el respaldo, no migra. `PG_DUMP` permite indicar el cliente PostgreSQL; en esta computadora se reconoce PostgreSQL 18.

`scripts.initialize` e `iniciar.ps1` aplican esta actualización mediante el mismo respaldo cuando detectan la revisión anterior. El procedimiento de actualización 7 queda fijado a su propia revisión para evitar que aplique versiones posteriores sin su verificación. Una instalación completamente nueva sigue aplicando el historial normal de migraciones y crea el administrador únicamente si no existe.

## Pruebas manuales por rol

1. **Superadministrador:** ingresa con `victor` y su contraseña actual. Abre Gestión de Usuarios; crea una Jefatura, un Operador y un Supervisor con usernames distintos y contraseñas iniciales seguras.
2. **Primer acceso:** ingresa con cada cuenta nueva. Debe aparecer el cambio obligatorio antes de permitir usar módulos. Cambia la contraseña y verifica que se abra el Dashboard correcto.
3. **Jefatura:** carga, consulta, edita, genera Excel e imprime un documento. Crea una cuenta de Operador o Supervisor. Comprueba que no puede escoger SUPERADMIN/JEFATURA, modificar otras cuentas privilegiadas, operar sobre `victor`, configurar servicios ni restaurar eliminados.
4. **Operador y Supervisor:** carga en cada módulo con servicio. La confirmación debe mostrar el código, con el formulario limpio y sin historial, edición, eliminación, impresión ni exportación. Prueba también las URLs administrativas directamente; deben devolver 403 sin modificar filas.
5. **Sesiones:** con una cuenta de carga abierta, cambia su rol, desactívala o restablece su contraseña desde otra sesión administrativa. La sesión anterior debe dejar de ser válida. Reactivar no debe recuperar esa sesión. Un restablecimiento vuelve a exigir cambio de contraseña.
6. **Eliminación:** con Superadministrador o Jefatura, abre Eliminar de un registro, proporciona motivo y confirma. Debe desaparecer de consultas e informes, pero permanecer en PostgreSQL. Sin confirmación o con una versión obsoleta, no debe modificarse.
7. **Restauración:** con Superadministrador, abre Registros eliminados, revisa VER DETALLE y restaura. Verifica el servicio, los datos originales y los eventos de eliminación/restauración. Jefatura debe recibir 403 si intenta esta función.
8. **Protección:** intenta modificar, restablecer o desactivar la cuenta protegida desde otra cuenta. Debe rechazarse. El cambio propio de contraseña exige la actual y conserva su protección.
9. **Actividad:** comprueba altas, roles, estados, cargas, ediciones, eliminación, informes y accesos en el historial. Las contraseñas no deben aparecer.
10. **Persistencia:** cierra sesión y reinicia únicamente la aplicación. Usuarios, roles, servicios, registros y auditorías deben conservarse.

Las cuentas nuevas para uso real deben ser creadas con los nombres y contraseñas institucionales correspondientes. No se crean usuarios ficticios ni registros de demostración en la base de uso.

## Pruebas automatizadas

La suite requiere una conexión `TEST_DATABASE_URL` a una base dedicada terminada en `_test`. Nunca utilices la base de la aplicación para ejecutar fixtures:

```powershell
.venv/Scripts/python.exe -m pytest -q
node --test tests/*.test.cjs
```

Las pruebas cubren los cuatro roles y los seis formularios, visibilidad y backend, primer acceso, contraseñas y confirmación, estados, privilegios de Jefatura, protección de `victor`, edición autorizada, eliminación lógica, detalle y restauración, exclusión de eliminados de Excel, auditoría, CSRF, sesiones revocadas y restablecimientos concurrentes con la autenticación. Las migraciones se comprueban en esquemas históricos aislados, conservando cuentas y registros.

Las pruebas anteriores que impedían a un Operador abrir formularios se actualizaron al nuevo requisito: ahora puede cargar, pero continúa sin consultar historial ni editar.

## Entrega

El paquete completo es `entregables/fuentes_actualizacion8.zip`. Incluye modelos, Blueprints, plantillas, scripts, migraciones, dependencias y pruebas. `entregables/ARCHIVOS_ACTUALIZACION_8.md` identifica los archivos nuevos y modificados. Se excluyen `.env`, datos de PostgreSQL, respaldos privados y muestras de prueba.

La implementación se concentra en `app/security/`, `app/models/user_audit.py`, `app/administration/record_access.py`, `record_lifecycle.py`, `record_print.py` y sus plantillas. Los módulos existentes incorporan los permisos, la auditoría y el filtro de eliminación, manteniendo sus formularios y reglas de registro.
