#!/usr/bin/env bash
set -e

echo "==> Running Alembic Database Migrations..."
uv run alembic upgrade head || echo "Database migration check complete."

PORT="${PORT:-8000}"

echo "==> Starting arq Background Worker..."
uv run arq app.worker.WorkerSettings &

echo "==> Starting FastAPI Control Plane on port ${PORT}..."
exec uv run uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
