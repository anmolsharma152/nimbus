# Nimbus

Nimbus is a cloud-native autonomous software engineering agent system (inspired by Devin). Users delegate software engineering tasks through a web product, while an isolated cloud workspace clones repositories, edits code, runs tests, captures output, and returns reviewable pull requests and tested patches.

**Engineered by [Anmol Sharma](https://linkedin.com/in/anmolsharma152)** | **[GitHub Profile](https://github.com/anmolsharma152)** | **[Live Portfolio](https://anmolsharma152.vercel.app)**

---

## Architecture Overview

* **Control Plane (`backend/`)**: FastAPI application providing REST API (`/api/tasks`) and real-time WebSocket event streaming (`/ws/tasks/{id}`) with history replay.
* **Worker & Queue (`backend/app/worker.py`)**: `arq` worker running over Redis, driving an autonomous agent loop powered by Google Gemini (`google-genai`).
* **Isolated Workspace (`backend/app/workspace.py`)**: Ephemeral Docker container sandbox that clones target repositories, configures git identity, creates task-specific feature branches (`nimbus/task-<id>`), runs commands, and captures diffs.
* **GitHub Integration (`backend/app/github_client.py`)**: Draft PR creator and branch pusher using GitHub REST API.
* **Web Frontend (`frontend/`)**: Modern Next.js 16 App Router interface featuring dark glassmorphism, prompt + repository inputs, real-time log streaming, and diff viewer.

---

## Repository Layout

```text
backend/                FastAPI control plane, Alembic migrations, arq worker, workspace adapter
frontend/               Next.js 16 web application
docs/                   Product architecture, roadmap, and security model
research/               Video transcript and foundational research inputs
docker-compose.yml      Local service orchestration
```

---

## Quickstart

### 1. Backend & Infrastructure

```bash
# Setup environment variables
cp .env.example .env # Ensure DATABASE_URL, REDIS_URL, and GEMINI_API_KEY are set

# Run Alembic migrations
cd backend
uv run alembic upgrade head

# Start API server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start Background Worker
uv run arq app.worker.WorkerSettings
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to create tasks and view live execution logs.
