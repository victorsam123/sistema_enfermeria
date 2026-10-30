$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$pythonExe = Join-Path (Get-Location) '.runtime/python/python.exe'
$pgBin = 'C:/Program Files/PostgreSQL/18/bin'
$dataDir = Join-Path (Get-Location) '.runtime/pgdata'
if (-not (Test-Path $pythonExe)) { throw 'No se encontró el Python portátil.' }
if (-not (Test-Path "$pgBin/initdb.exe")) { throw 'No se encontró PostgreSQL 18.' }
if (-not (Test-Path '.env')) {
    & $pythonExe -s -c "import secrets; from pathlib import Path; p=secrets.token_hex(24); Path('.env').write_text('APP_ENV=development\nSECRET_KEY='+secrets.token_hex(32)+'\nDATABASE_URL=postgresql+psycopg://enfermeria_owner:'+p+'@127.0.0.1:55432/enfermeria\nINITIAL_ADMIN_PASSWORD=513625\nTRUSTED_HOSTS=localhost,127.0.0.1\nSESSION_COOKIE_SECURE=false\nTRUST_PROXY=false\n'); Path('.runtime/pg-password').write_text(p)"
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo generar la configuración.' }
}
if (-not (Test-Path "$dataDir/PG_VERSION")) {
    if (-not (Test-Path '.runtime/pg-password')) { throw 'Falta la contraseña de inicialización. Revisa .env sin sobrescribir datos existentes.' }
    & "$pgBin/initdb.exe" -D $dataDir -U enfermeria_owner -A scram-sha-256 --pwfile=.runtime/pg-password --encoding=UTF8 --locale=C
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo inicializar el clúster local.' }
    Remove-Item -LiteralPath '.runtime/pg-password'
}
& "$pgBin/pg_ctl.exe" status -D $dataDir *> $null
if ($LASTEXITCODE -ne 0) {
    # pg_ctl inicia PostgreSQL sin abrir una ventana interactiva.
    & "$pgBin/pg_ctl.exe" start -D $dataDir -l .runtime/postgres.log -o '-h 127.0.0.1 -p 55432' -w
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo iniciar PostgreSQL local.' }
}
& $pythonExe -s -c "from dotenv import load_dotenv; load_dotenv(); import os, psycopg; from psycopg import sql; from psycopg.conninfo import conninfo_to_dict; d=conninfo_to_dict(os.environ['DATABASE_URL'].replace('postgresql+psycopg://','postgresql://')); name=d.pop('dbname'); c=psycopg.connect(**d,dbname='postgres',autocommit=True); exists=c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone(); c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name))) if not exists else None; c.close()"
if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar la base de datos.' }
& $pythonExe -s -m scripts.initialize
if ($LASTEXITCODE -ne 0) { throw 'No se pudo completar la inicialización.' }
Write-Host 'Entorno local listo. Ejecutar: .runtime/python/python.exe -m waitress --listen=127.0.0.1:5000 run:app'
