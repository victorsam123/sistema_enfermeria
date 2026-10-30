# Departamento de Enfermería · Hospital Regional CDE

La preparación para publicar en `victorsam123/sistema_enfermeria` y desplegar con Docker, PostgreSQL y volumen persistente en Railway está en [DESPLIEGUE.md](DESPLIEGUE.md). Esa guía reemplaza las instrucciones generales de Railway al final de este documento para el nuevo despliegue.

Aplicación Flask con autenticación real en PostgreSQL, SQLAlchemy, Flask-Login, Flask-WTF y Alembic/Flask-Migrate. Incluye autenticación, auditoría, Dashboard, Justificativo, Reposo, cambios de guardia normales y pagados, Vacaciones y Comisionados. El registro de reposos sigue la foto 3 e incluye cálculo de días, diagnóstico y entrega al Departamento. Bootstrap 5.3.8 y Bootstrap Icons 1.13.1 están incluidos localmente, con sus licencias: el navegador no depende de un CDN.

La [guía de la actualización 3](ACTUALIZACION_3.md) detalla los módulos, archivos completos, migración y pruebas paso a paso. Para actualizar una instalación existente, conserva `.env` y los datos y ejecuta `flask --app run db upgrade`; no necesitas recrear la base ni inicializar el administrador.

La [guía de la actualización 4](ACTUALIZACION_4.md) detalla Comisionados y Vacaciones. La [guía vigente de la actualización 5](ACTUALIZACION_5.md) describe el registro completo de Reposo, la migración `0004_reposos`, los archivos y las instrucciones de prueba. Reposo conserva también sus accesos anteriores a los cambios de guardia.

La [guía de la actualización 6](ACTUALIZACION_6.md) detalla las correcciones de navegación, los cambios de guardia con varias fechas y horarios independientes y la fecha de cobertura opcional de Justificativo.

La [guía de la actualización 7](ACTUALIZACION_7.md) explica los 14 servicios hospitalarios, la selección obligatoria, las carpetas virtuales, configuración, reclasificación con historial e informes Excel privados. El archivo Excel se mantiene únicamente como referencia del catálogo, sin importar sus registros.

La [guía vigente de la actualización 8](ACTUALIZACION_8.md) describe Gestión de Usuarios, los roles SUPERADMIN/JEFATURA/OPERADOR/SUPERVISOR, sus permisos centralizados, cambio obligatorio de contraseña inicial, auditoría y eliminación lógica con restauración. La revisión actual es `0007_usuarios_roles_eliminacion`. Para actualizar desde la versión 7, detén el servidor, instala las dependencias y ejecuta `python scripts/migrar_actualizacion8.py`, que verifica un respaldo antes de migrar y conserva la contraseña de victor. Al finalizar, inicia sesión nuevamente.

## Ejecutar en esta computadora

La planilla de vacaciones ahora usa el formato Excel oficial `app/assets/planilla_vacaciones_2026_2027.xlsx`, disponible para imprimir y descargar desde Vacaciones. La revisión `0011_carrera_funcionarios` agrega la carrera a la ficha sin inventar datos para funcionarios existentes; complétala al editar cada ficha. Los rubros son **111** para Lic. en Enfermería y **142** para Tec. en Enfermería. Ejecuta `python -m flask --app run db upgrade` para aplicar la migración en una instalación existente.

La [guía vigente de la actualización 11](ACTUALIZACION_11.md) agrega vínculos laborales con fechas y antigüedades independientes dentro de una sola ficha. El total se calcula por vínculos activos y las correcciones quedan auditadas. La revisión de vínculos laborales es `0010_vinculos_laborales`. Detén el servidor y ejecuta `python -m scripts.migrar_actualizacion11` para respaldar y migrar desde la versión 10. Se conserva la fecha inicial como vínculo 1 y el contador anterior como referencia, sin inventar vínculos adicionales ni duplicar fotografías.

La [guía vigente de la actualización 10](ACTUALIZACION_10.md) incorpora **Funcionario**: fichas únicas por cédula, edad/antigüedad de calendario, fotografía privada e historial para Superadministrador y Jefatura. Operadores/Supervisores cuentan con una búsqueda mínima dentro de formularios de carga. La revisión vigente es `0009_funcionarios`; para actualizar desde la versión 9, detén el servidor y ejecuta `python -m scripts.migrar_actualizacion10`, que verifica un respaldo conjunto y conserva todos los datos anteriores. No vincula históricos por coincidencia de nombres ni carga fichas ficticias.

La [guía vigente de la actualización 9](ACTUALIZACION_9.md) incorpora fotografías opcionales en los seis formularios, almacenamiento privado persistente local/S3, galerías protegidas, retiros con historial, indicadores Excel y respaldo conjunto. La revisión vigente es `0008_documentos_adjuntos`. Detén el servidor y ejecuta `python -m scripts.migrar_actualizacion9` para respaldar y migrar desde la actualización 8. Conserva `instance/` junto con `.env` al actualizar. Antes de Railway configura S3 o un volumen persistente: los archivos sensibles nunca se guardan en `static`.

Se incluye un entorno Python portátil **local, no versionado** en `.runtime/python`, y un clúster PostgreSQL independiente en `.runtime/pgdata`. Usa los binarios de PostgreSQL 18 ya instalados. Escucha exclusivamente en `127.0.0.1:55432`; no modifica el servicio PostgreSQL del puerto 5432. `.env` contiene las credenciales aleatorias locales y no debe compartirse.

Desde PowerShell, en esta carpeta:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_local.ps1
.runtime/python/python.exe -s -m waitress --listen=127.0.0.1:5000 run:app
```

Abre **http://127.0.0.1:5000**. Usuario inicial: `victor`; contraseña inicial: `513625`. El script aplica migraciones y crea el administrador solo si no existe. Repetirlo no cambia su contraseña ni borra registros. Ctrl+C detiene la aplicación; PostgreSQL permanece activo y conserva los datos.

En los siguientes arranques también puedes usar `powershell -NoProfile -ExecutionPolicy Bypass -File iniciar.ps1`, que prepara la base local e inicia la aplicación en un solo paso. Si el puerto 5000 ya está ocupado por una ejecución anterior, usa esa instancia o ciérrala antes de iniciar otra.

Para detener el PostgreSQL de este proyecto después de cerrar la aplicación:

```powershell
& 'C:/Program Files/PostgreSQL/18/bin/pg_ctl.exe' stop -D "$PWD/.runtime/pgdata" -m fast
```

No borres `.runtime/pgdata`: contiene la base local. Haz copias con `pg_dump` antes de actualizaciones o traslados. El entorno portátil es una comodidad para esta computadora; para instalar en otra utiliza el procedimiento siguiente.

## Instalación estándar en Windows

1. Instala Python 3.12 o 3.13 desde python.org, con el lanzador `py`, y PostgreSQL 16 o posterior. Conserva la contraseña elegida al instalar PostgreSQL.
2. Abre PowerShell en el proyecto y crea un entorno:

```powershell
py -3 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.venv/Scripts/python.exe -c "import secrets; print(secrets.token_hex(32))"
```

`requirements.lock.txt` contiene las versiones exactas verificadas en Windows con Python 3.13; puedes instalarlo con `python -m pip install -r requirements.lock.txt` para reproducir ese entorno.

3. Coloca la clave generada en `SECRET_KEY` dentro de `.env`. No uses la clave de ejemplo ni regeneres la clave en cada arranque.
4. En SQL Shell o pgAdmin, conectado como propietario del servidor, crea una base y un propietario exclusivo. `\password` solicita la contraseña sin incluirla en el SQL:

```sql
CREATE ROLE enfermeria_owner LOGIN;
\password enfermeria_owner
CREATE DATABASE enfermeria OWNER enfermeria_owner;
```

5. Configura `.env` con la dirección real de PostgreSQL:

```dotenv
DATABASE_URL=postgresql+psycopg://enfermeria_owner:CONTRASENA_CODIFICADA@localhost:5432/enfermeria
INITIAL_ADMIN_PASSWORD=513625
APP_ENV=development
SESSION_COOKIE_SECURE=false
TRUSTED_HOSTS=localhost,127.0.0.1
TRUST_PROXY=false
```

Codifica caracteres especiales de usuario/contraseña como componentes URL (por ejemplo `@` se representa como `%40`). Nunca publiques `.env` ni imprimas su contenido en registros.

6. Inicializa y ejecuta:

```powershell
.venv/Scripts/python.exe -m scripts.initialize
.venv/Scripts/python.exe -m waitress --listen=127.0.0.1:5000 run:app
```

La inicialización es explícita: no se conecta a PostgreSQL ni crea tablas por cada importación o solicitud. No se utiliza `create_all` ni `drop_all`. Si las tablas ya existen por otro sistema sin historial Alembic, revisa y prepara una migración de adopción antes de ejecutar; no borres ni sobrescribas la base.

## Protección del administrador y contraseñas

`victor` es único, activo, protegido y Superadministrador. El hash scrypt se almacena en `password_hash`; la contraseña nunca se registra. El servicio de inicialización utiliza un bloqueo transaccional PostgreSQL y conserva íntegramente una cuenta existente. Si detecta una cuenta existente incompatible, falla y solicita revisión sin modificarla.

Las validaciones ORM rechazan eliminar, desproteger, desactivar o cambiar identidad/rol de una cuenta protegida. PostgreSQL aplica además CHECK y triggers para UPDATE/DELETE, incluso con SQL directo, y rechaza TRUNCATE. El downgrade inicial se bloquea para evitar borrar datos. El propietario o un superusuario PostgreSQL puede modificar el esquema y desactivar triggers: las barreras protegen frente a operaciones accidentales, no frente a quien controla el servidor. La cuenta de ejecución en producción debe carecer de privilegios DDL y no ser propietaria de las tablas.

Tras la primera inicialización, retira `INITIAL_ADMIN_PASSWORD` de `.env`. Cambia la contraseña inicial antes de exponer la aplicación:

```powershell
.venv/Scripts/python.exe -m flask --app run change-admin-password
```

El comando solicita y confirma la contraseña sin mostrarla, exige 12 caracteres y conserva la protección. Las sesiones asociadas al hash anterior dejan de ser válidas. Para el Python portátil sustituye `.venv/Scripts/python.exe` por `.runtime/python/python.exe -s`.

## Comprobación manual

1. En una ventana privada abre `/`: debe redirigir a `/login`.
2. Accede con `victor` y `513625` si todavía no cambiaste la contraseña. Debe aparecer el Dashboard y PostgreSQL debe verificarse con `SELECT 1`.
3. Una contraseña errónea o un usuario inexistente producen el mismo mensaje. Tras cinco envíos en 15 minutos por IP o cuenta, se responde 429; el contador persiste entre procesos y reinicios.
4. Usa el menú de perfil para cerrar sesión. Regresar a `/` debe pedir credenciales; `/logout` solo admite POST con CSRF.
5. Reinicia la aplicación y vuelve a ejecutar la inicialización. La cuenta y el hash deben conservarse. Consulta `usuarios` y `logs_acceso` con pgAdmin sin exponer hashes ni secretos.

Los eventos `login_exitoso`, `login_fallido`, `limite_intentos` y `logout` registran hora UTC e IP de conexión. No se confía en encabezados de IP enviados por clientes. Sesión de 30 minutos, cookie HttpOnly/SameSite, protección CSRF, encabezados CSP y respuestas sin caché. No se admiten redirecciones de retorno arbitrarias tras el login. El contador PostgreSQL funciona entre trabajadores sin Redis. Usuarios de una misma IP comparten su límite; esto es deliberado y puede requerir ajuste para una red institucional.

## Pruebas automatizadas contra PostgreSQL real

Usa una base **exclusiva** cuyo nombre termine en `_test`. Las pruebas aplican migraciones y dejan sus datos en esa base; nunca deben ejecutarse contra producción. No utilizan SQLite. Crea `enfermeria_test` y proporciona la conexión mediante una variable de proceso. Si falta, pytest omite las pruebas explícitamente.

```powershell
# Crea enfermeria_test con el mismo procedimiento de creación de base.
# Coloca la conexión de pruebas en una variable de entorno local, sin versionarla.
$env:TEST_DATABASE_URL = 'postgresql+psycopg://USUARIO:CLAVE@localhost:5432/enfermeria_test'
.venv/Scripts/python.exe -m pytest -q
Remove-Item Env:TEST_DATABASE_URL
```

Las pruebas comprueban credenciales, CSRF, rutas restringidas, roles, logout, auditoría, bloqueo de intentos, persistencia al recrear la aplicación, inicialización idempotente, cambio de contraseña y protección ORM/SQL/TRUNCATE.

## Estructura y crecimiento

### Actualización 2: reloj y accesos administrativos

Esta sección describe la base creada en la actualización 2. Desde la actualización 3, Justificativo, Reposo y Cambio de Guardia están habilitados según [la guía vigente](ACTUALIZACION_3.md); únicamente Vacaciones y Comisionados mantienen el aviso de desarrollo.

La actualización 4 habilita también Vacaciones y Comisionados; los avisos descritos a continuación corresponden a la etapa 2 original.

El Dashboard muestra fecha `DD/MM/AAAA` y hora `HH:MM:SS` de `America/Asuncion`. La hora inicial y las reglas horarias provienen de Python `zoneinfo` y `tzdata`; el navegador avanza con un reloj monotónico cada segundo y se sincroniza con `/api/reloj` cada minuto y al volver a la pestaña. No utiliza la hora ni la zona horaria configuradas en el dispositivo. La referencia de hora es el reloj del servidor, que debe mantenerse sincronizado por el sistema operativo. El endpoint requiere el mismo rol y sesión que el Dashboard y no renueva la duración de la sesión.

Los accesos Justificativo, Reposo, Cambio de Guardia, Vacaciones y Comisionados se definen en `app/dashboard_modules.py`. Actualmente abren un diálogo accesible con el aviso «Este módulo se encuentra en desarrollo». No contienen formularios, registros ni lógica de negocio. Para habilitar un módulo futuro, registra su Blueprint en la factoría y asigna su endpoint al acceso correspondiente; la plantilla generará el enlace con `url_for`.

Esta ampliación no necesita migraciones ni inicialización de base de datos. Después de actualizar los archivos, reinicia únicamente el proceso Flask/Waitress/Gunicorn y recarga el Dashboard. No ejecutes un restablecimiento de contraseñas ni de datos. Conserva `.env` y la base existente.

Comprobación del reloj y de los avisos con Node.js (sin instalar paquetes):

```powershell
node --test tests/dashboard-ui.test.cjs
```

Las pruebas de Python incluyen el cambio de fecha en Paraguay, su horario en julio, el endpoint protegido y la presencia de las cinco tarjetas. Se usa `tzdata>=2025.1` para incluir la actualización de Paraguay de [IANA 2025a](https://www.iana.org/time-zones/releases/2025a); [Python recomienda tzdata para Windows](https://docs.python.org/3/library/zoneinfo.html).

```text
app/
  __init__.py          Factoría de aplicación, comandos y errores
  extensions.py       SQLAlchemy, LoginManager, Migrate, CSRF
  models/             Usuario, LogAcceso e IntentoLogin
  routes/             Blueprints de autenticación e inicio
  services.py         Inicialización, auditoría y limitación compartida
  templates/          Base, login, Dashboard y errores
  static/             CSS, JavaScript y dependencias visuales locales
migrations/           Historial Alembic y triggers PostgreSQL
scripts/              Inicialización y entorno local
tests/                Integración real PostgreSQL
config.py             Configuración ambiental
run.py                Entrada WSGI
```

Para módulos futuros, añade modelos, un Blueprint y una migración revisada. Protege cada ruta con `role_required` y configura los roles admitidos. No dependas de ocultar enlaces. No añadas campos o funcionalidades hospitalarias hasta definir su alcance.

```powershell
.venv/Scripts/python.exe -m flask --app run db migrate -m "Descripción del cambio"
# Revisa el archivo generado y realiza una copia de seguridad.
.venv/Scripts/python.exe -m flask --app run db upgrade
.venv/Scripts/python.exe -m flask --app run init-admin
```

## Railway u otro servicio Python/PostgreSQL

El proyecto está preparado mediante `Procfile`, `requirements.txt` y `scripts.initialize`; no se ha publicado en un servicio externo. Usa Python 3.13. Variables: `DATABASE_URL` (PostgreSQL), `SECRET_KEY` aleatoria estable, `APP_ENV=production`, `SESSION_COOKIE_SECURE=true`, `TRUSTED_HOSTS=tu-dominio` y `INITIAL_ADMIN_PASSWORD` solo en el primer despliegue. Usa HTTPS y SSL de PostgreSQL según el proveedor (`?sslmode=require` cuando corresponda). Configura un trabajo previo al despliegue: `python -m scripts.initialize`. Inicio: `gunicorn --bind 0.0.0.0:$PORT --workers 2 run:app`.

Solo activa `TRUST_PROXY=true` si existe exactamente un proxy confiable que sobrescribe los encabezados Forwarded y bloquea acceso directo al proceso. En caso contrario, mantén false y audita la IP del par directo. Limita `TRUSTED_HOSTS` a los dominios reales.

En producción utiliza un propietario de migraciones separado. Ejecuta la inicialización con sus credenciales; después configura `DATABASE_URL` con una cuenta de ejecución sin privilegios de propietario. Concede CONNECT a la base, USAGE del esquema y las secuencias necesarias. Los módulos requieren SELECT/INSERT/UPDATE en sus tablas y detalles, el catálogo SELECT/INSERT/UPDATE y el historial administrativo SELECT/INSERT. La autenticación conserva sus permisos para usuarios, logs e intentos. No concedas UPDATE/DELETE del historial ni DELETE del catálogo; la aplicación no ofrece eliminación permanente de registros. No concedas CREATE, ALTER, DROP, TRUNCATE ni pertenencia al rol propietario a la cuenta de ejecución. Usa backups del proveedor y verifica su restauración. Revisa migraciones generadas antes de cada despliegue: ninguna herramienta puede asegurar la conservación de tablas frente a futuras migraciones deliberadamente destructivas. Para esta actualización existente, `scripts.initialize` requiere clientes pg_dump/pg_restore y conserva un respaldo previo; consulta la guía 7 antes del despliegue.

Referencias de implementación: [seguridad de Flask](https://flask.palletsprojects.com/en/stable/web-security/) y [triggers PostgreSQL](https://www.postgresql.org/docs/current/sql-createtrigger.html).
