$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_local.ps1
if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar el entorno local.' }
Write-Host 'Sistema disponible en http://127.0.0.1:5000. Ctrl+C para detener la aplicación.'
& .runtime/python/python.exe -s -m waitress --listen=127.0.0.1:5000 run:app
