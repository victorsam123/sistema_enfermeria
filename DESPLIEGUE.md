# GitHub y Railway

Repositorio previsto: https://github.com/victorsam123/sistema_enfermeria.git

## Publicar el código

El repositorio Git local usa la rama `main` y el remoto `origin`. Antes de publicar, revisa `git status` y luego ejecuta:

```powershell
git push -u origin main
```

GitHub puede solicitar iniciar sesión. Si el remoto ya tiene commits, primero inspecciona e integra su historial; no uses `--force`. `.env`, `.runtime/`, `instance/`, respaldos y ZIP de entregas están excluidos. Los datos clínicos y las fotografías no se trasladan mediante Git. GitHub Actions ejecutará las pruebas con PostgreSQL 18 y Node 22.

## Crear el servicio en Railway

1. Crea un proyecto con PostgreSQL y un servicio conectado al repositorio, rama `main`, directorio raíz `/`.
2. Railway detecta el `Dockerfile`; usa su comando de inicio predeterminado. No establezcas un comando previo al despliegue: la inicialización ocurre en el arranque, con el volumen ya montado.
3. Añade un volumen al servicio web, montado en `/data`. Usa una sola réplica. Las fotografías se guardan en `/data/documentos_privados`, fuera del directorio público.
4. Genera el dominio público del servicio y configura las variables siguientes antes de desplegar:

| Variable | Valor |
| --- | --- |
| `DATABASE_URL` | Referencia a `${{Postgres.DATABASE_URL}}`; sustituye `Postgres` si tu servicio tiene otro nombre |
| `SECRET_KEY` | Clave aleatoria estable de al menos 32 caracteres; genera con `python -c "import secrets; print(secrets.token_hex(32))"` |
| `INITIAL_ADMIN_PASSWORD` | Contraseña nueva, privada, de al menos 12 caracteres para la primera instalación |
| `APP_ENV` | `production` |
| `SESSION_COOKIE_SECURE` | `true` |
| `TRUSTED_HOSTS` | `tu-dominio.up.railway.app,healthcheck.railway.app`; añade tu dominio propio si corresponde |
| `TRUST_PROXY` | `false`; activar únicamente tras verificar la topología de proxy indicada en README |
| `DOCUMENT_STORAGE_BACKEND` | `local` |
| `DOCUMENT_LOCAL_ROOT` | `/data/documentos_privados` |
| `DOCUMENT_LOCAL_PERSISTENT` | `true` |

Railway proporciona `PORT`; Gunicorn escucha en `0.0.0.0` y ese puerto. El arranque aplica las migraciones y crea `victor` solo si no existe; conserva su contraseña en reinicios. Si falla la inicialización, el servidor no arranca.

5. En Settings del servicio configura Healthcheck Path `/health` y timeout 300 segundos. Devuelve 200 cuando PostgreSQL responde y 503 si no está disponible, sin mostrar datos ni credenciales.
6. Despliega y accede por HTTPS. Inicia sesión con `victor` y la contraseña privada configurada. Retira `INITIAL_ADMIN_PASSWORD` después de la primera inicialización. Reinicia y verifica que los registros y una fotografía de prueba autorizada persistan.

El contenedor usa Python 3.13 y `postgresql-client`, que proporciona `pg_dump` y `pg_restore` para respaldar y verificar las migraciones históricas que lo requieren. Confirma que la versión del cliente sea compatible con la del servidor PostgreSQL. Las dependencias de Python se instalan desde `requirements.txt`; el lock existente corresponde a la instalación Windows. Para trasladar una base histórica, respáldala y verifica su restauración con herramientas compatibles antes de migrarla o moverla.

## Trasladar la instalación local existente

Un despliegue con PostgreSQL vacío crea una instalación nueva. Para conservar la información real, detén las escrituras, respalda PostgreSQL con `pg_dump` compatible y copia también los objetos privados, conservando sus claves y estructura. Restaura en una base vacía de Railway y transfiere los archivos al volumen privado o a S3; no los subas al repositorio. Comprueba revisión Alembic, cantidades y `flask --app run conciliar-documentos --verificar` antes de abrir el servicio. Conserva el respaldo original y comprueba la restauración antes del cambio definitivo.

Para posteriores migraciones usa un rol propietario distinto de la cuenta web, según README, y un proceso de mantenimiento con respaldo verificado. Con esa separación, ejecuta la inicialización como propietario y sustituye el comando de inicio del servicio por `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --access-logfile - --error-logfile - run:app` con `DATABASE_URL` del rol web. El arranque automático predeterminado requiere permisos de migración.

## Referencias oficiales

- [Desplegar Flask con Dockerfile](https://docs.railway.com/guides/flask)
- [Volúmenes persistentes](https://docs.railway.com/volumes)
- [Verificaciones de salud y hostname permitido](https://docs.railway.com/deployments/healthchecks)
- [Comandos previos al despliegue y sus límites de acceso a volúmenes](https://docs.railway.com/deployments/pre-deploy-command)

La preparación local no publica el repositorio ni crea recursos de Railway. Las credenciales y recursos externos se configuran en sus plataformas.
