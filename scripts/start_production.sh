#!/bin/sh
set -eu

# Inicializar al arrancar: Railway monta los volúmenes en esta etapa.
python -m scripts.initialize
# Importación única opcional: define IMPORTAR_FUNCIONARIOS_URL (CSV de la hoja) y retírala después.
# Es idempotente y un fallo no impide el arranque.
if [ -n "${IMPORTAR_FUNCIONARIOS_URL:-}" ]; then
    python -m scripts.importar_funcionarios "$IMPORTAR_FUNCIONARIOS_URL" --aplicar || echo "Importación de funcionarios falló; se continúa."
fi
exec gunicorn --bind "0.0.0.0:${PORT:-8080}" --workers 2 --timeout 120 --access-logfile - --error-logfile - run:app
