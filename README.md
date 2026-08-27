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
[![Docker](https://img.shields.io/badge/Docker-Sandboxed%20microVM-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![3-Tier LLM](https://img.shields.io/badge/LLM-3--Tier%20Multi--LLM%20Routing-8E75B2?logo=google&logoColor=white)](https://ai.google.dev)
[![Tests](https://img.shields.io/badge/Tests-46%2F46%20Passing-brightgreen?logo=pytest&logoColor=white)](#testing--evals-benchmark)

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
    participant LLM as Google Gemini 2.5 (Agent Loop)
    participant Sandbox as Docker Sandbox (/workspace/repo)
    participant GitHub as GitHub REST API

    Dev->>UI: Submit Task Prompt + Target Repo URL
    UI->>API: POST /api/tasks
    API->>DB: Insert Task record (status: PENDING)
    API->>Redis: Enqueue run_agent_loop(task_id, prompt, repo_url)
    API-->>UI: Return task_id
    UI->>API: Open WebSocket /ws/tasks/{task_id}
    
    Redis->>Worker: Dequeue task job
    Worker->>DB: Update Task (status: RUNNING)
    Worker->>API: Broadcast status: running
    API-->>UI: Stream status badge: RUNNING
    
    Worker->>Sandbox: Provision ephemeral container & git clone
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
    Worker->>Sandbox: Commit changes & git push branch
    Worker->>GitHub: POST /repos/{owner}/{repo}/pulls (Draft PR)
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
        Secrets["Secret Vault\n(GEMINI_API_KEY, GITHUB_TOKEN)"]
        LLM["Google Gemini 2.5\n(Structured Reasoning)"]
    end

    subgraph Untrusted Zone ["⚠️ Untrusted Ephemeral Sandbox (Docker / microVM)"]
        Container["Disposable Container Sandbox\n• Memory Cap: 1 GB\n• CPU Limit: 2.0 Cores\n• PIDs Limit: 256\n• Cap Drop: ALL\n• No New Privileges\n• Timeout: 300s"]
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
        [*] --> WorkspaceInit: Provision Ephemeral Docker Container
        WorkspaceInit --> GitClone: Clone repo & create branch nimbus/task-<id>
        GitClone --> ReasoningLoop: Initialize Gemini 2.5 Agent
        
        state ReasoningLoop {
            PlanAction --> EmittingCommand: Generate structured JSON
            EmittingCommand --> ExecutingInSandbox: Run command inside container
            ExecutingInSandbox --> EvaluatingFeedback: Inspect stdout/stderr & test exit code
            EvaluatingFeedback --> PlanAction: Refine fix & repeat
        }
        
        ReasoningLoop --> DiffExtraction: Agent signals completion
        DiffExtraction --> CommitAndPush: Commit changes & push branch
        CommitAndPush --> OpenDraftPR: Create GitHub Draft PR
    }

    RUNNING --> COMPLETED: Success (Patch captured & PR opened)
    RUNNING --> FAILED: Agent exception / syntax failure
    PENDING --> CANCELLED: User cancels task
    RUNNING --> CANCELLED: User cancels task
    
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
  * Asynchronous Docker container execution wrappers (`asyncio.to_thread`) preventing I/O starvation.
* **🛡️ Zero-Trust Workspace Isolation**:
  * Ephemeral Docker sandbox per task with hard resource limits (`1 GB` RAM, `2.0` CPUs, PID cap `256`, dropped capabilities, and strict execution timeouts).
  * Secrets are kept outside the sandbox—GitHub authentication is injected via transient basic headers without writing credentials into `.git/config`.
* **🔄 Append-Only Event Sourcing & Instant Replay**:
  * Every log, bash command, terminal output, and status change is persisted in PostgreSQL as a durable `TaskEvent`.
  * Interrupted browser sessions reconnect to `/ws/tasks/{id}` and instantly receive full historical playback.
* **🛑 Real-Time Task Cancellation**:
  * `POST /api/tasks/{task_id}/cancel` endpoint instantly signals running workers and cleans up Docker resources.
* **🚀 Automated GitHub Draft PRs**:
  * Automatically provisions feature branches (`nimbus/task-<task_id>`), commits changes, pushes to remote, and creates Draft Pull Requests with patch diff previews.

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
│   │   ├── models.py         # SQLAlchemy relational models (Task, TaskEvent)
│   │   ├── settings.py       # Pydantic configuration & env variable schema
│   │   ├── worker.py         # arq background worker & async Gemini agent loop
│   │   └── workspace.py      # Ephemeral Docker workspace sandbox adapter
│   ├── evals/                # Benchmark runner & automated eval suite
│   ├── tests/                # 17 comprehensive unit & integration tests
│   ├── Dockerfile.workspace  # Pre-built sandbox workspace container definition
│   └── pyproject.toml        # uv package manager configuration
├── frontend/
│   ├── src/app/
│   │   ├── layout.tsx        # App layout with Geist typography & metadata
│   │   ├── page.tsx          # Task submission dashboard (prompt + repo URL)
│   │   └── tasks/[id]/       # Real-time streaming terminal & patch diff inspector
│   └── package.json          # Next.js 16 + React 19 + TypeScript config
├── docs/
│   ├── architecture.md       # Full architecture specification & sequence diagrams
│   ├── roadmap.md            # Multi-phase milestone delivery roadmap
│   └── security.md           # Security model & container trust boundaries
├── TASKS.md                  # Project task tracker & milestone checklist
├── PROJECT_STATE.md          # Up-to-date development status & technical audit
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
GEMINI_API_KEY=your_google_gemini_api_key
GITHUB_TOKEN=your_github_token_for_prs  # Optional
```

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

```text
============================== test session starts ==============================
collected 46 items

tests/test_api.py ........                                               [ 17%]
tests/test_auth.py ........                                              [ 34%]
tests/test_browser.py ...                                                [ 41%]
tests/test_credentials.py .....                                          [ 52%]
tests/test_evals.py ..                                                   [ 56%]
tests/test_github_client.py ...                                          [ 63%]
tests/test_llm.py ....                                                   [ 71%]
tests/test_scaling.py ....                                               [ 80%]
tests/test_worker.py ....                                                [ 89%]
tests/test_workspace.py .....                                            [100%]

============================== 46 passed in 7.43s ==============================
```

### Running Autonomous Agent Evaluation Benchmark

```bash
cd backend
uv run python evals/eval_runner.py
```

---

## 🗺️ Multi-Phase Roadmap Status

| Phase | Milestone | Status | Key Deliverables |
| :--- | :--- | :---: | :--- |
| **Phase 0** | Foundation & Durable State | ✅ **Completed** | FastAPI, Postgres asyncpg, Alembic migrations, Redis arq queue, WebSocket gateway |
| **Phase 1** | Safe Single-Agent Execution | ✅ **Completed** | Isolated Docker sandbox, async Gemini loop, git diff extraction, Next.js UI |
| **Phase 2** | Multi-Tenant GitHub Workflow | ✅ **Completed** | Ephemeral token injection, branch isolation (`nimbus/task-<id>`), automated Draft PRs |
| **Phase 3** | Product-Grade Scalability | 🔄 **In Progress** | Distributed Redis Pub/Sub, session reconnect replay, MicroVM provider interface |
| **Phase 4** | Browser Automation & Cloud Deploy | 📋 **Planned** | Playwright visual verification, screenshot artifacts, production multi-cloud deploy |

---

## 📄 License & Attribution

Developed with ❤️ by **[Anmol Sharma](https://linkedin.com/in/anmolsharma152)**. Released under the [MIT License](LICENSE).
