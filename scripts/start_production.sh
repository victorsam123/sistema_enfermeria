#!/bin/sh
set -eu

# Inicializar al arrancar: Railway monta los volúmenes en esta etapa.
python -m scripts.initialize
exec gunicorn --bind "0.0.0.0:${PORT:-8080}" --workers 2 --timeout 120 --access-logfile - --error-logfile - run:app
