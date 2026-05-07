#!/usr/bin/env bash
# ==============================================================================
# Entrypoint do container — Railway / Docker
# ==============================================================================
# 1. Garante que o diretório de dados exista (volume montado)
# 2. Roda migrações Alembic (cria/atualiza schema no Postgres)
# 3. Inicia gunicorn servindo site/web_app.py:app
# ==============================================================================

set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
PORT="${PORT:-8080}"
WORKERS="${GUNICORN_WORKERS:-2}"
THREADS="${GUNICORN_THREADS:-4}"
TIMEOUT="${GUNICORN_TIMEOUT:-120}"

mkdir -p "${DATA_DIR}"

echo "[start] DATA_DIR=${DATA_DIR}"
echo "[start] PORT=${PORT}"

# ----------------------------------------------------------------------------
# Migrações Alembic (auth.db -> Postgres)
# ----------------------------------------------------------------------------
# Em desenvolvimento (DATABASE_URL apontando para sqlite local), pulamos.
# Em produção, falha de migração derruba o container -> Railway reinicia.
# ----------------------------------------------------------------------------
if [ -n "${DATABASE_URL:-}" ]; then
    echo "[start] Rodando alembic upgrade head..."
    alembic upgrade head
else
    echo "[start] DATABASE_URL não definido — pulando migrações."
fi

# ----------------------------------------------------------------------------
# Gunicorn
# ----------------------------------------------------------------------------
# --chdir /app/site faz o módulo `web_app` ser importável diretamente,
# preservando o bootstrap de sys.path/cwd que web_app.py já faz.
# ----------------------------------------------------------------------------
echo "[start] Iniciando gunicorn (workers=${WORKERS} threads=${THREADS})..."
exec gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers "${WORKERS}" \
    --threads "${THREADS}" \
    --timeout "${TIMEOUT}" \
    --access-logfile - \
    --error-logfile - \
    --chdir /app/site \
    web_app:app
