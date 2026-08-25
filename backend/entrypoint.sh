#!/usr/bin/env bash
set -e

echo "==> Running Alembic Database Migrations..."
uv run alembic upgrade head

PORT="${PORT:-8000}"

if [ "$SERVICE_TYPE" = "worker" ]; then
    echo "==> Starting arq Background Worker..."
    exec uv run arq app.worker.WorkerSettings
else
    echo "==> Starting FastAPI Control Plane on port ${PORT}..."
    exec uv run uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
fi
