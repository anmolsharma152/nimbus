<div align="center">

# ☁️ Nimbus

### **Autonomous Cloud Software Engineering Agent Platform**

*Delegate coding tasks to an isolated, disposable cloud sandbox that inspects repositories, modifies code, runs test suites, captures tested patches, and opens GitHub Pull Requests with live streaming visibility.*

[![Live Demo](https://img.shields.io/badge/Live%20Demo-nimbusagent.vercel.app-000000?style=for-the-badge&logo=vercel&logoColor=white)](https://nimbusagent.vercel.app/)

[![Python 3.13+](https://img.shields.io/badge/Python-3.13%2B-blue?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js 16](https://img.shields.io/badge/Next.js-16.3%20(Turbopack)-black?logo=next.js&logoColor=white)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20(asyncpg)-336791?logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7%20(arq)-DC382D?logo=redis&logoColor=white)](https://redis.io)
[![Docker](https://img.shields.io/badge/Sandbox-Docker%20%2F%20subprocess-2496ED?logo=docker&logoColor=white)](docs/security.md)
[![3-Tier LLM](https://img.shields.io/badge/LLM-3--Tier%20Multi--LLM%20Routing-8E75B2?logo=google&logoColor=white)](https://ai.google.dev)
[![Tests](https://img.shields.io/badge/Tests-pytest%20%2B%20vitest%20in%20CI-brightgreen?logo=pytest&logoColor=white)](#-testing--evals-benchmark)

<p align="center">
  <b>🌐 <a href="https://nimbusagent.vercel.app/">Live Web App</a></b> &nbsp;|&nbsp;
  <b>Engineered by <a href="https://linkedin.com/in/anmolsharma152">Anmol Sharma</a></b> &nbsp;|&nbsp;
  <b><a href="https://github.com/anmolsharma152">GitHub</a></b> &nbsp;|&nbsp;
  <b><a href="https://anmolsharma152.vercel.app">Live Portfolio</a></b>
</p>

</div>

---

## 🏛️ System Architecture

<details>
<summary><b>🔍 Click to expand: End-to-End Sequence Diagram</b></summary>
<br>

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer (Browser)
    participant UI as Next.js 16 Web UI
    participant API as FastAPI Control Plane
    participant DB as PostgreSQL (Asyncpg)
    participant Redis as Redis / arq Queue
    participant Worker as arq Background Worker
    participant LLM as 3-Tier LLM (Gemini → Groq → OpenRouter)
    participant Sandbox as Workspace Sandbox (Docker / subprocess)
    participant GitHub as GitHub REST API

    Dev->>UI: Sign in with GitHub, submit Task Prompt + Target Repo
    UI->>API: POST /api/tasks (repo tasks require sign-in)
    API->>DB: Insert Task record (status: PENDING)
    API->>Redis: Enqueue run_agent_loop(task_id, prompt, repo_url)
    API-->>UI: Return task_id
    UI->>API: Open WebSocket /ws/tasks/{task_id}?ticket=...
    
    Redis->>Worker: Dequeue task job
    Worker->>DB: Update Task (status: RUNNING)
    Worker->>API: Broadcast status: running
    API-->>UI: Stream status badge: RUNNING
    
    Worker->>GitHub: GET /repos/{owner}/{repo} (check access as the user)
    Worker->>Sandbox: Provision ephemeral workspace & git clone
    Worker->>Sandbox: git checkout -b nimbus/task-<task_id>
    
    loop Agent Execution Loop (up to 20 turns)
        Worker->>LLM: Send Task Goal + Working Dir Context
        LLM-->>Worker: JSON Tool Command (e.g. bash command)
        Worker->>API: Broadcast command event
        API-->>UI: Stream $ command to Terminal
        Worker->>Sandbox: Execute command in background thread
        Sandbox-->>Worker: Exit code + stdout / stderr
        Worker->>API: Broadcast result event
        API-->>UI: Stream terminal output & test results
    end
    
    Worker->>Sandbox: git add -N . && git diff HEAD
    Sandbox-->>Worker: Capture patch_diff
    Worker->>Sandbox: Replay patch on fresh clone & push (to a fork if no write access)
    Worker->>GitHub: POST /repos/{owner}/{repo}/pulls (Draft PR into the default branch)
    GitHub-->>Worker: Return PR URL
    Worker->>DB: Save patch_diff, pr_url, status: COMPLETED
    Worker->>API: Broadcast status: completed + PR link
    API-->>UI: Render "View Draft PR" Button & Patch Diff Viewer
```

</details>

---

## 🔒 Trust Boundaries & Security Isolation

<details>
<summary><b>🔍 Click to expand: Security & Trust Boundary Architecture</b></summary>
<br>

```mermaid
graph TD
    subgraph Trusted Zone ["🔒 Trusted Control Plane (Host / Cloud Cluster)"]
        UI["Web Frontend\n(Next.js 16 App Router)"]
        API["FastAPI Gateway\n(REST & WebSockets)"]
        DB[("PostgreSQL 16\n(Tasks & Append-Only Events)")]
        Redis[("Redis 7\n(arq Queue + Pub/Sub)")]
        Worker["arq Background Worker\n(Non-blocking Async Loop)"]
        Secrets["Encrypted Vault\n(user OAuth tokens, BYOK keys)"]
        LLM["3-Tier LLM Router\n(Gemini → Groq → OpenRouter)"]
    end

    subgraph Untrusted Zone ["⚠️ Untrusted Ephemeral Sandbox"]
        Container["Disposable Workspace\nDocker: 1 GB / 2 CPU / 256 PIDs, cap drop ALL\nSubprocess (prod): per-task UID, scrubbed env\nCommand timeout: 300s"]
        Repo["/workspace/repo\nCloned Repository Code"]
        Tools["Sandboxed Toolchain\n(git, python3, build-essential)"]
    end

    UI <-->|HTTPS / WSS| API
    API <--> DB
    API <--> Redis
    Redis <--> Worker
    Worker <--> DB
    Worker --- Secrets
    Worker <-->|REST API| LLM
    Worker -->|Async Threadpool / isolated pipe| Container
    Container --- Repo
    Container --- Tools
    Worker -->|Transient Auth Header| GitHub["GitHub API\n(Draft Pull Request)"]
```

</details>

---

## ⚡ Task State Machine

<details>
<summary><b>🔍 Click to expand: Task Lifecycle State Machine</b></summary>
<br>

```mermaid
stateDiagram-v2
    [*] --> PENDING: User delegates task via UI / API
    PENDING --> RUNNING: Worker dequeues from Redis
    
    state RUNNING {
        [*] --> WorkspaceInit: Check repo access & provision workspace
        WorkspaceInit --> GitClone: Clone repo & create branch nimbus/task-<id> (follow-ups restore earlier changes)
        GitClone --> ReasoningLoop: Initialize 3-tier LLM agent
        
        state ReasoningLoop {
            PlanAction --> EmittingCommand: Generate structured JSON
            EmittingCommand --> ExecutingInSandbox: Run command inside container
            ExecutingInSandbox --> EvaluatingFeedback: Inspect stdout/stderr & test exit code
            EvaluatingFeedback --> PlanAction: Refine fix & repeat
        }
        
        ReasoningLoop --> DiffExtraction: Agent signals completion
        DiffExtraction --> CommitAndPush: Commit changes & push branch
        CommitAndPush --> OpenDraftPR: Create Draft PR (or update the existing one)
    }

    RUNNING --> COMPLETED: Success (Patch captured & PR opened)
    RUNNING --> FAILED: Agent exception / syntax failure
    PENDING --> CANCELLED: User cancels task
    RUNNING --> CANCELLED: User cancels task
    COMPLETED --> PENDING: Follow-up message or retry
    FAILED --> PENDING: Follow-up message or retry
    CANCELLED --> PENDING: Follow-up message or retry
    
    COMPLETED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
```

</details>

---

## 💻 Web UI & Live Terminal Experience

The Next.js 16 frontend provides a modern glassmorphic split-pane dashboard:

```text
+---------------------------------------------------------------------------------------+
|  <- Back   Task #42   🌱 nimbus/task-42              [🚀 View Draft PR] [🟢 COMPLETED] |
+-------------------------------------------+-------------------------------------------+
| 🎯 USER GOAL                              | 🖥️ AGENT EXECUTION TERMINAL               |
|                                           |                                           |
| "Fix authentication middleware bug and    | 10:40:12 Agent initialized workspace      |
| add unit tests for token verification"    | 10:40:14 $ git status                     |
|                                           | 10:40:15 On branch nimbus/task-42         |
| 📁 REPOSITORY                             | 10:40:18 $ pytest tests/test_auth.py      |
| https://github.com/org/repo               | 10:40:20 [Exit code: 1] 1 test failed     |
|                                           | 10:40:24 $ python3 fix_auth.py            |
| 📝 GENERATED PATCH DIFF        [Collapse] | 10:40:27 $ pytest tests/test_auth.py      |
| +---------------------------------------+ | 10:40:30 [Exit code: 0] 5 passed in 0.4s  |
| | diff --git a/auth.py b/auth.py        | | 10:40:32 Agent finished: Verified fix!    |
| | + if not token: raise AuthError()     | | 10:40:35 Draft PR opened successfully!  |
| | - if token == None: pass              | |                                         |
| +---------------------------------------+ |                                           |
+-------------------------------------------+-------------------------------------------+
```

---

## 🌟 Key Features

* **⚡ 100% Non-Blocking Asynchronous Core**:
  * FastAPI with `asyncpg` connection pooling (`pool_size=20`, `max_overflow=10`, `pool_pre_ping=True`).
  * Asynchronous LLM reasoning using Google GenAI's native async client (`client.aio.chats`).
  * Blocking Docker and subprocess calls run in `asyncio.to_thread` so they never stall the event loop.
* **🛡️ Workspace Isolation**:
  * One disposable workspace per task. With Docker: `1 GB` RAM, `2.0` CPUs, `256` PIDs, dropped capabilities. In production (Render, no Docker daemon): a per-task unprivileged UID with a scrubbed environment, without resource caps. See [docs/security.md](docs/security.md).
  * The GitHub token never enters the workspace: clone and push run outside the agent's user, and the push replays the agent's patch onto a fresh clone.
* **🔐 Safe Repo Access**:
  * Repo tasks require GitHub sign-in and use only the user's own token; there is no server-wide token.
  * Protected branch names are rejected, and pushes use `--force-with-lease`, so Nimbus never touches a branch it didn't create.
  * Access is checked before a run; without write access, changes go to a fork in the user's account.
* **🔄 Append-Only Event Sourcing & Instant Replay**:
  * Every log, bash command, terminal output, and status change is persisted in PostgreSQL as a durable `TaskEvent`.
  * Interrupted browser sessions reconnect to `/ws/tasks/{id}` and instantly receive full historical playback.
* **🛑 Real-Time Task Cancellation**:
  * `POST /api/tasks/{task_id}/cancel` endpoint instantly signals running workers and cleans up Docker resources.
* **🚀 Automated GitHub Draft PRs**:
  * Automatically provisions feature branches (`nimbus/task-<task_id>`), commits changes, pushes, and opens Draft Pull Requests into the repo's default branch.
* **💬 Follow-ups on the Same Task**:
  * `POST /api/tasks/{id}/messages` continues a finished task from its changes so far and updates the same branch and PR.

---

## 📁 Repository Layout

```text
Nimbus/
├── backend/
│   ├── alembic/              # Database migration scripts & environment
│   ├── app/
│   │   ├── db.py             # SQLAlchemy 2.0 async engine & connection pool setup
│   │   ├── github_client.py  # GitHub REST API client for Draft PRs & branch pushes
│   │   ├── main.py           # FastAPI control plane, REST routes & WebSocket gateway
│   │   ├── models.py         # SQLAlchemy models (User, UserCredential, Task, TaskEvent, TaskMessage)
│   │   ├── settings.py       # Pydantic configuration & env variable schema
│   │   ├── worker.py         # arq background worker & async Gemini agent loop
│   │   └── workspace.py      # Ephemeral Docker workspace sandbox adapter
│   ├── evals/                # Benchmark runner & automated eval suite
│   ├── tests/                # pytest suite (mocked; no DB, Redis, Docker or LLM calls)
│   ├── Dockerfile.workspace  # Pre-built sandbox workspace container definition
│   └── pyproject.toml        # uv package manager configuration
├── frontend/
│   ├── src/app/
│   │   ├── layout.tsx        # App layout with Geist typography & metadata
│   │   ├── page.tsx          # Task submission dashboard (prompt + repo URL)
│   │   └── tasks/[id]/       # Real-time streaming terminal & patch diff inspector
│   └── package.json          # Next.js 16 + React 19 + TypeScript config
├── docs/
│   ├── cloud_deployment.md   # Render / Neon / Upstash / Vercel deployment guide
│   ├── roadmap.md            # Short roadmap: done and next
│   └── security.md           # Security model: what is enforced and what isn't built yet
├── ARCHITECTURE.md           # Architecture specification & sequence diagrams
├── TASKS.md                  # Project task tracker & milestone checklist
├── AGENTS.md / CLAUDE.md     # Instructions for coding agents
├── docker-compose.yml        # Local multi-service infrastructure setup
└── .env.example              # Environment variables template
```

---

## 🚀 Quickstart & Setup

### 1. Prerequisites
* **Python 3.13+** with [`uv`](https://docs.astral.sh/uv/) installed.
* **Node.js 18+** & `npm`.
* **Docker** running locally.
* **PostgreSQL 16** & **Redis 7** (or via Docker Compose).

### 2. Environment Configuration

```bash
cp .env.example .env
```

Ensure `.env` contains:
```ini
DATABASE_URL=postgresql+asyncpg://nimbus_user:nimbus_password@localhost:5432/nimbus_db
REDIS_URL=redis://localhost:6379/0
GEMINI_API_KEY=your_google_gemini_api_key   # or GROQ_API_KEY / OPENROUTER_API_KEY
GITHUB_CLIENT_ID=your_oauth_app_client_id    # GitHub OAuth app: sign-in is required for repo tasks
GITHUB_CLIENT_SECRET=your_oauth_app_client_secret
JWT_SECRET_KEY=a_long_random_secret          # also derives the credential-vault key
```

There is no server-wide GitHub token: repo tasks clone, push and open PRs with the signed-in user's own OAuth token (or a PAT they save in Settings).

### 3. Backend Setup

```bash
cd backend

# Run database migrations
uv run alembic upgrade head

# Start FastAPI control plane (Terminal 1)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start arq background worker (Terminal 2)
uv run arq app.worker.WorkerSettings
```

### 4. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start Next.js development server (Terminal 3)
npm run dev
```

Open [**http://localhost:3000**](http://localhost:3000) to submit tasks and inspect live streaming execution!

---

## 🧪 Testing & Evals Benchmark

### Running Backend Unit & Integration Tests

```bash
cd backend
uv run pytest
```

Everything is mocked (no DB, Redis, Docker or LLM calls). CI also enforces a 78% coverage floor (`uv run pytest --cov`) and runs the frontend checks: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`.

### Running the Agent Evaluation

```bash
cd backend
uv run python evals/eval_runner.py                    # all fixture cases
uv run python evals/eval_runner.py --case slugify --json scorecard.json
```

Runs the real agent loop against small fixture repos and scores each run with hidden tests. It uses the LLM keys from `.env`, so it consumes provider quota. `tests/test_evals.py` checks the harness with a scripted LLM.

---

## 🗺️ Roadmap

Phases 0–5 (agent loop, GitHub PRs, OAuth, vault, event fan-out, screenshots, evals) and a security/reliability hardening pass are done. Next up: the task-page UX, production workspace limits, and a microVM workspace provider. See [docs/roadmap.md](docs/roadmap.md) and [TASKS.md](TASKS.md).

---

## 📄 License & Attribution

Developed with ❤️ by **[Anmol Sharma](https://linkedin.com/in/anmolsharma152)**. Released under the [MIT License](LICENSE).
