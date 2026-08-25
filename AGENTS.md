# Repository Guidelines

## Project Structure & Module Organization

Nimbus is organized into distinct services and modules:

- `backend/`: FastAPI control-plane API (`app/main.py`), ORM models (`app/models.py`), Alembic database migrations (`alembic/`), `arq` background worker (`app/worker.py`), Docker workspace isolation (`app/workspace.py`), and GitHub REST client (`app/github_client.py`).
- `frontend/`: Next.js 16 web application with dark glassmorphic UI, task submission, and live WebSocket log/command streaming with patch inspection.
- `docs/`: Product architecture, delivery roadmap, and security model.
- `research/`: Video transcript and foundational research inputs.
- `docker-compose.yml`: Local multi-service infrastructure setup.

## Development & Test Commands

### Backend
```bash
cd backend
uv run alembic upgrade head                    # run database migrations
uv run uvicorn app.main:app --port 8000 --reload # run FastAPI control-plane
uv run arq app.worker.WorkerSettings          # run background worker
```

### Frontend
```bash
cd frontend
npm run dev    # start Next.js dev server
npm run build  # build production Next.js app
```

## Coding Style & Conventions

- **Python**: Standard PEP 8, 4-space indentation, `snake_case` functions/variables, async/await for I/O operations (`httpx`, `asyncpg`, `arq`).
- **TypeScript / React**: Modern functional components, React hooks, Next.js App Router, CSS modules for scoped styling.
- **Security**: Do not commit secrets (`.env`). Workspaces are treated as untrusted and isolated via Docker containers.
