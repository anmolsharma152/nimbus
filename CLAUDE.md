# CLAUDE.md

Nimbus is an autonomous cloud coding agent. A FastAPI control plane queues tasks, an `arq` worker runs an LLM tool loop inside an ephemeral Docker (or subprocess) workspace, and a Next.js frontend streams events over WebSocket. See also `AGENTS.md`, `ARCHITECTURE.md`, `docs/security.md`.

## Build & Dependency Management

Backend: Python 3.13, managed with **uv** (`backend/pyproject.toml`, `backend/uv.lock`).
```bash
cd backend
uv sync                      # create .venv + install deps (incl. dev group: pytest, pytest-asyncio)
uv sync --frozen --no-dev    # production install (what backend/Dockerfile does)
docker build -f Dockerfile.workspace -t nimbus-workspace .   # required for Docker mode (WORKSPACE_IMAGE); agent runs as uid 10001
```
Frontend: Node 20, **npm**, Next.js 16.3 / React 19.2 (read `frontend/AGENTS.md`: this Next version has breaking changes).
```bash
cd frontend
npm install
npm run build
```
Config: copy `.env.example` → `.env` (settings load `.env` and `../.env`). Key vars: `DATABASE_URL`, `REDIS_URL`, `GEMINI_API_KEY` / `GROQ_API_KEY` / `OPENROUTER_API_KEY` (at least one needed to run tasks), `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` (OAuth), `JWT_SECRET_KEY` (also derives the Fernet key for the credential vault, so rotating it breaks stored secrets), `FRONTEND_URL`, `API_INTERNAL_URL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`.

System prerequisites: PostgreSQL 16, Redis (optional: without it, `enqueue_task` runs the agent in-process), Docker daemon (optional: without it, `SubprocessWorkspace` runs commands on the host, as a per-task UID with a scrubbed env when the worker is root, as on Render).

Token rule: anything holding the GitHub token (clone, push) runs outside the agent's user and never reads the agent's `.git`; push replays the agent's patch onto a fresh clone (`app/workspace.py`, "Token-safe git operations").

## Run Commands

```bash
cd backend
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000 --reload
uv run arq app.worker.WorkerSettings
uv run python evals/eval_runner.py        # real agent loop on fixture repos (calls your LLM keys)

cd frontend && npm run dev                # http://localhost:3000
```
Production (`backend/entrypoint.sh`): migrations, then worker in background + uvicorn in one container (Render/Railway).

## Testing Commands

```bash
cd backend
uv run pytest                                   # full suite (all mocked; no DB/Redis/Docker needed)
uv run pytest tests/test_workspace.py           # single file
uv run pytest tests/test_api.py::test_create_task_endpoint   # single test
uv run --with pytest-cov pytest --cov=app --cov-report=term-missing
```
There are no frontend tests.

## Code Style & Guidelines

- Lint/format (no config is committed yet; run ad hoc): `uvx ruff check app tests evals`, `uvx ruff format`. Frontend: `npm run lint` (eslint, `eslint-config-next`), typecheck `./node_modules/.bin/tsc --noEmit` (do not use `npx tsc`, which installs the wrong package).
- Python: PEP 8, 4 spaces, `snake_case`, async/await for all I/O. Blocking SDKs (docker-py, subprocess) go through `asyncio.to_thread` (see `UnifiedWorkspace`).
- Request/response shapes are Pydantic `BaseModel`s declared in the router module. Errors surface as `HTTPException`. Ownership failures return **404**, not 403.
- Workspace methods return `(exit_code, output)` tuples instead of raising. Callers must check the code.
- Enums are stored upper-case (`TaskStatus`, `EventType`) and serialized lower-case to clients.
- Logging: `logger = logging.getLogger(__name__)`, never `print()`. `app/logging_config.py` adds request_id/task_id to every record; pass structured fields via `extra={"event": ...}`. Never log prompts, tokens or keys (log lengths/ids instead). Each task emits one `task_finished` line (status, duration, iterations, LLM tier usage).
- TypeScript: functional components + hooks, App Router, CSS modules per page/component.
- Never commit `.env`. Treat everything executed inside a workspace (LLM output, cloned repo contents) as untrusted.

## Architecture Overview

```
frontend (Next.js) ──REST──▶ app/main.py (FastAPI)
      ▲  WS /ws/tasks/{id}         │ create Task row → enqueue_task (arq/Redis, else in-process)
      │                            ▼
      │                     app/worker.py run_agent_loop
      │                       ├─ decrypt BYOK keys (app/security.py, models.UserCredential)
      │                       ├─ app/workspace.py UnifiedWorkspace → DockerWorkspace | SubprocessWorkspace
      │                       ├─ app/llm.py LLMChatSession: Gemini → Groq → OpenRouter failover
      │                       ├─ loop: LLM emits ```json {"command": ...}``` → exec → feed output back
      │                       └─ diff → commit → push → app/github_client.create_draft_pr
      │                     log_event(): TaskEvent row + Redis pub/sub (app/events.py)
      └── manager.broadcast ◀── HTTP POST /api/internal/tasks/{id}/events (worker → API)
```
- `app/auth.py`: GitHub OAuth, JWT in the `nimbus_session` cookie or a Bearer token. `app/credentials.py`: encrypted BYOK vault + onboarding. `app/ratelimit.py`: per-user concurrency/hourly quotas.
- `app/db.py`: async SQLAlchemy engine (asyncpg). Schema lives in Alembic **and** in ad-hoc `ALTER TABLE` statements in `main.lifespan`.
- Live streaming currently depends on the worker's HTTP POST to the internal endpoint. The Redis `subscribe_task` path in `events.py` is never consumed, so cross-replica fan-out does not work.
