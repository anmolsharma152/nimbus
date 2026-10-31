# Nimbus — System Architecture & Design Specification

> **Autonomous Cloud Software Engineering Agent Platform**  
> *Architected for Zero-Trust Sandbox Isolation, Multi-Tenant Security, Multi-Tier LLM Resilience, and Append-Only Flight Telemetry.*

---

## 1. System Overview & Executive Summary

**Nimbus** is a Devin-style autonomous cloud software engineering platform. Developers delegate natural-language coding tasks via a modern web interface. A trusted cloud control plane provisions an isolated, disposable sandbox to inspect repositories, write code modifications directly to disk, execute test suites, capture tested patches, and open verified GitHub Pull Requests.

```
                                  [ Developer Browser ]
                                           │
                                           ▼
                       [ Frontend: Next.js 16 (App Router / Turbopack) ]
                         (Dark Glassmorphic UI / Replay / Lightbox)
                                           │
                       ┌───────────────────┴───────────────────┐
                       │ HTTPS REST / OAuth                    │ WSS Authenticated Stream
                       ▼                                       ▼
               [ Backend: FastAPI Control Plane Gateway (Render / Cloud) ]
                       │                                       │
       Postgres Async  │                       Distributed     │ Pub/Sub &
       Connection Pool │                       Event Bus       │ Stream Fan-Out
                       ▼                                       ▼
          [ PostgreSQL 16 (Neon / Supabase) ]        [ Redis 7 (Upstash / Cloud) ]
          • Users & Encrypted Credentials            • arq Job Queue
          • Tasks & Append-Only Event Stream         • Real-Time Flight Fan-Out
                       ▲                                       ▲
                       │ Async State Updates                   │ Dequeue Job
                       │                                       │
               [ Background Worker: arq Worker Process ]
                       │
       ┌───────────────┼───────────────────────────────┐
       ▼               ▼                               ▼
[ 3-Tier Multi-LLM ] [ Ephemeral Sandbox ]      [ GitHub REST API ]
  • Gemini 3.6/3.7     • Docker (local)           • Access check / fork
  • Groq 120B          • Subprocess (production)  • Feature Branches
  • OpenRouter Free    • MicroVM (planned)        • Automated Draft PRs
```

---

## 2. Core Architectural Pillars

### 2.1. Hexagonal Control-Plane vs. Data-Plane Separation
The orchestrator lives **strictly outside** the untrusted workspace. The control plane manages task lifecycle, authentication, secret decryption, and LLM reasoning. The execution data plane (the sandbox) has no access to control-plane credentials, database connections, or LLM API keys. Commands are executed over isolated pipes (`docker exec` or `subprocess.run`).

### 2.2. Ephemeral Sandboxing
Every task executes inside a fresh, disposable workspace with a 300-second per-command timeout and a 30-minute task limit, removed when the task ends, fails or is cancelled. Two implementations exist:
- **DockerWorkspace** (local / any host with a Docker daemon): container as uid 10001 with `1 GB` RAM, `2.0` CPUs, `256` PIDs, `cap_drop=ALL`, `no-new-privileges:true`.
- **SubprocessWorkspace** (production on Render, which has no Docker daemon): commands run as a per-task unprivileged UID with a scrubbed environment. It has **no** CPU/memory/PID limits and no network restrictions.

See `docs/security.md` for the full model and what is not built yet.

### 2.3. Resilient 3-Tier Multi-LLM Fallback Router
To guarantee 99.9% uptime despite third-party provider outages, rate limits, and 429/503 spikes:
- **Tier 1 (Primary)**: Google Gemini pool (`gemini-3.6-flash`, `gemini-3.7-flash`, `gemini-3.5-flash`, `gemini-flash-latest`) via `google-genai` async client.
- **Tier 2 (Secondary)**: Groq (`openai/gpt-oss-120b`) with context window truncation (5,500 tokens) to stay within the 8k TPM cap.
- **Tier 3 (Tertiary)**: OpenRouter (`cohere/north-mini-code:free` or `google/gemma-4-31b-it:free`).

### 2.4. Append-Only Event Sourcing & Distributed Fan-Out
All state mutations (logs, bash commands, exit codes, stdout/stderr chunks, visual screenshots, and status transitions) are persisted to PostgreSQL as immutable `TaskEvent` rows. Real-time updates fan out across horizontally scaled API replicas via **Redis Pub/Sub & Streams**. Connecting WebSocket clients instantly receive full historical replay.

### 2.5. Server-Backed Encrypted Credential Vault & BYOK Routing
Developer GitHub OAuth tokens and optional BYOK (Bring-Your-Own-Key) provider keys (`gemini`, `groq`, `openrouter`, `github_pat`) are encrypted at rest with **Fernet**, using a key derived from `JWT_SECRET_KEY`. There is no server-wide GitHub token: repo tasks require sign-in and use only the owner's own credentials. Credentials are never stored client-side.

### 2.6. Safe Branch Delivery & Follow-ups
- Before a repo task runs, the worker checks the owner's access (`GET /repos/{owner}/{repo}`). With write access the branch is pushed to the repo; without it, to a fork in the owner's account. The draft PR always targets the repo's **default branch**.
- Pushes use `--force-with-lease`: a first push can only create a new branch (protected names like `main` are also rejected up front), and later pushes only replace the commit Nimbus pushed last.
- A **follow-up** (`POST /api/tasks/{id}/messages`) re-runs the same task: the workspace is rebuilt from the task's base commit plus its changes so far, the agent gets the goal and all follow-ups, and the same branch and PR are updated. **Retry** starts over from a clean checkout but keeps the branch and PR.

---

## 3. End-to-End Execution Sequence Flow

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer (Browser)
    participant UI as Next.js 16 Web UI
    participant API as FastAPI Control Plane
    participant DB as PostgreSQL 16 (Asyncpg)
    participant Redis as Redis 7 (Queue + Pub/Sub)
    participant Worker as arq Background Worker
    participant Vault as Fernet Secret Vault
    participant LLM as 3-Tier Multi-LLM Router
    participant Sandbox as Ephemeral Workspace
    participant GitHub as GitHub REST API

    Dev->>UI: Submit Task Prompt + Target Repo
    UI->>API: POST /api/tasks (Bearer JWT)
    API->>API: Check Rate Limits & Concurrency Quotas
    API->>DB: Insert Task record (status: PENDING)
    API->>Redis: Enqueue run_agent_loop(task_id)
    API-->>UI: Return task_id
    UI->>API: POST /api/tasks/{id}/stream-ticket (session cookie via /api proxy)
    API-->>UI: 60s task-scoped ticket
    UI->>API: Open WebSocket /ws/tasks/{id}?ticket={ticket}
    API->>DB: Query & Stream Historical Events
    API-->>UI: Replay Historical Stream

    Redis->>Worker: Dequeue task job
    Worker->>DB: Update Task (status: RUNNING)
    Worker->>Redis: Publish status: running
    Redis->>API: Pub/Sub Broadcast
    API-->>UI: Stream status badge: RUNNING

    Worker->>Vault: Decrypt User OAuth Token & BYOK Keys
    Worker->>GitHub: GET /repos/{owner}/{repo} (access check as the owner)
    Worker->>Sandbox: Provision sandbox & clone repo (branch: nimbus/task-<id>)
    Worker->>Sandbox: git config user.name & user.email (Author Attribution)

    loop Agent Reasoning & Tool Loop (up to 20 turns)
        Worker->>LLM: Send Goal + Context + Tool Output
        LLM-->>Worker: JSON Tool Command {"command": "...", "screenshot": "..."}
        Worker->>DB: Persist TaskEvent (COMMAND)
        Worker->>Redis: Publish command event
        Redis->>API: Pub/Sub Broadcast
        API-->>UI: Stream $ command to Terminal Flight Recorder
        Worker->>Sandbox: Execute command in isolated threadpool
        Sandbox-->>Worker: Exit code + stdout/stderr + optional screenshot
        Worker->>DB: Persist TaskEvent (RESULT)
        Worker->>Redis: Publish result / screenshot event
        Redis->>API: Pub/Sub Broadcast
        API-->>UI: Stream terminal output & update Visual Preview Gallery
    end

    Worker->>Sandbox: git add -N . && git diff HEAD
    Sandbox-->>Worker: Capture patch_diff
    opt No write access
        Worker->>GitHub: POST /repos/{owner}/{repo}/forks
    end
    Worker->>Sandbox: Replay patch on a fresh clone & push (force-with-lease) to repo or fork
    Worker->>GitHub: POST /repos/{owner}/{repo}/pulls (Draft PR into default branch; skipped if the task already has one)
    GitHub-->>Worker: HTML PR URL
    Worker->>DB: Save patch_diff, pr_url, status: COMPLETED
    Worker->>Redis: Publish status: completed
    Redis->>API: Pub/Sub Broadcast
    API-->>UI: Render "View Draft PR" CTA & Interactive Diff Viewer
```

---

## 4. Trust Boundaries & Security Architecture

```mermaid
graph TD
    subgraph Trusted Zone ["🔒 Trusted Control Plane (Control Plane & Infrastructure)"]
        UI["Web Frontend\n(Next.js 16 App Router)"]
        API["FastAPI Control Plane Gateway\n(REST & WebSockets)"]
        DB[("PostgreSQL 16\n(Users, Vault, Tasks, Events)")]
        Redis[("Redis 7\n(arq Queue, Pub/Sub, Streams)")]
        Worker["arq Background Worker Process"]
        Vault["Fernet AES-256 Vault\n(Encrypted BYOK & OAuth Tokens)"]
        LLM["3-Tier LLM Router\n(Gemini, Groq, OpenRouter)"]
    end

    subgraph Untrusted Zone ["⚠️ Untrusted Disposable Sandbox (Data Plane)"]
        Container["Disposable Sandbox\nDocker: 1 GB / 2 CPU / 256 PIDs, cap drop ALL\nSubprocess (prod): per-task UID, scrubbed env\nCommand timeout: 300s"]
        Repo["/workspace/repo\nCloned Repository Code"]
        Tools["Toolchain\n(git, python3, build-essential)"]
    end

    UI <-->|HTTPS / WSS (JWT Auth)| API
    API <-->|asyncpg pool (20 conn)| DB
    API <-->|Redis Pub/Sub / Streams| Redis
    Redis <-->|Job Dispatch| Worker
    Worker <-->|State Updates| DB
    Worker --- Vault
    Worker <-->|Async REST / SDK| LLM
    Worker -->|docker exec / isolated pipe| Container
    Container --- Repo
    Container --- Tools
    Worker -->|Transient Auth Header| GitHub["GitHub REST API\n(Draft Pull Requests)"]
```

### Security Controls Matrix

| Attack Vector | Vulnerability Risk | Nimbus Mitigation Strategy |
| :--- | :--- | :--- |
| **Credential Theft in Repo** | Malicious script in repository reads environment secrets | Control plane holds all keys. Secrets are **never** injected into sandbox environment variables or `.git/config`. |
| **Sandbox Escape / Privilege Escalation** | Container breakout attacking host system | Docker: `cap_drop=["ALL"]`, `no-new-privileges`, `pids_limit=256`, non-root uid. Subprocess (prod): per-task unprivileged UID only. |
| **Denial of Service / Fork Bombs** | Infinite loops, heavy compilation, or fork bombs | Docker: cgroup limits (`1 GB` RAM, `2.0` CPUs, `256` PIDs). Both: 300 s per-command timeout and 30 min task limit. Subprocess mode has no resource caps. |
| **Unauthorized Repo Writes** | Anonymous users or agents pushing to someone's default branch | Repo tasks need sign-in and the owner's own token; protected branch names rejected; force-with-lease pushes never touch a branch Nimbus didn't create. |
| **LLM Provider Outages / Rate Limits** | 429 quota exhaustion or 503 provider downtime | 3-tier hierarchical router with intra-model Gemini failover, Groq context truncation, and OpenRouter backup. |
| **Session Hijacking / Stream Snooping** | Unauthorized users observing competitor flight logs | Authenticated WebSocket handshakes verifying JWT tokens and owner-scoped database queries (`user_id`). |
| **Noisy Neighbors / Sandbox Monopolization** | Single user submitting hundreds of concurrent tasks | Per-user limits counting new tasks and follow-ups (Free: 3 concurrent / 20 per hour; Pro: 10 / 100); signed-out visitors share 2 concurrent / `ANON_TASKS_PER_HOUR` (10). |

---

## 5. Architectural Trade-Off Analysis

| Architectural Decision | Chosen Strategy | Alternative Rejected | Rationale & Trade-Off |
| :--- | :--- | :--- | :--- |
| **Orchestrator Placement** | Out-of-Sandbox Control Plane | In-Sandbox Agent Process | Running the agent inside the sandbox simplifies tool execution but exposes LLM API keys and database credentials to untrusted code. |
| **Workspace Lifecycle** | Ephemeral per-task sandbox | Stateful persistent container | Ephemeral containers prevent cross-task contamination and eliminate persistent storage costs, at the minor cost of cloning per task. |
| **Git Credential Injection** | Token-bearing git runs outside the agent's user, header via `GIT_CONFIG_*` env | Persisted `.git/config` token | The agent never sees the token, and its git config or hooks can't affect the push (the patch is replayed on a fresh clone). |
| **Event Persistence** | PostgreSQL Append-Only Stream | Ephemeral In-Memory State | Enables full historical session playback on browser disconnects, compliance audits, and post-flight debugging. |
| **Event Broadcasting** | Redis Pub/Sub + Streams | Local In-Process Memory Bus | Enables horizontal scaling of FastAPI gateway replicas across distributed cloud instances without dropping events. |
| **LLM Reasoning Format** | Structured JSON with Bash Tools | Native Python Functions / LSP | Standard bash tool invocation gives universal flexibility across all languages without requiring heavy language servers. |
| **Visual Verification** | Base64 Artifact Extraction | Heavy Full-VNC Streaming | Binary base64 snapshot capture provides instant visual feedback without the bandwidth and compute overhead of a full VNC stack. |

---

## 6. Technical Stack & Component Contracts

### 6.1. Backend Control Plane (`backend/`)
- **FastAPI 0.141+**: Asynchronous ASGI REST API and WebSocket gateway.
- **SQLAlchemy 2.0 + asyncpg**: Connection-pooled asynchronous PostgreSQL ORM (`pool_size=20`, `max_overflow=10`, `pool_pre_ping=True`).
- **Alembic**: schema migrations (latest `d4e5f6a7b8c9`: follow-up messages and branch state). `main.lifespan` also creates tables and adds missing columns at startup.
- **arq 0.26+ & Redis 7**: Non-blocking asynchronous job queue and distributed event bus.
- **Cryptography (Fernet AES-256)**: Encryption of user OAuth tokens and BYOK credentials at rest.
- **Google GenAI SDK & HTTPX**: Asynchronous multi-turn LLM reasoning clients.

### 6.2. Frontend Web Console (`frontend/`)
- **Next.js 16 (App Router) & React 19**: Server and client component architecture with Turbopack.
- **CSS Modules & Dark Glassmorphism**: High-contrast, tactile UI with custom SVG vector icons.
- **3-Tab Task Inspector**: Terminal Flight Recorder, Interactive Patch Diff Viewer, and Visual Preview Gallery with Lightbox modal.
- **AuthContext & OAuth Navigation**: Automatic session token management and 1-click GitHub Sign-In.

---

## 7. Cloud Production Deployment Topology

Nimbus is deployed across a multi-service modern cloud infrastructure:

- **Frontend**: [Vercel](https://vercel.com) Edge Network (`https://nimbusagent.vercel.app`) with Next.js 16.
- **Control Plane API + Worker**: one [Render](https://render.com) Docker web service (`nimbus-api`). `backend/entrypoint.sh` runs migrations, starts the `arq` worker in the background, then Uvicorn. Render has no Docker daemon, so tasks use SubprocessWorkspace.
- **Database**: [Neon](https://neon.tech) Serverless PostgreSQL 16 with connection pooling.
- **Distributed Event Bus & Queue**: [Upstash](https://upstash.com) Managed Redis 7 (TLS enabled).
- **Monitoring**: UptimeRobot keep-alive pings against `GET /api/health` ensuring zero cold starts.

---

## 8. Evaluation Benchmark & Verification Architecture

`backend/evals/eval_runner.py` runs the same command loop as the worker (`app/agent.py`) on small fixture repos (factorial edge case, slugify implementation, calculator bug):
1. Each case seeds and commits a fixture repo in a real workspace (Docker or subprocess), then gives the agent the task prompt using the configured LLM tiers.
2. After the agent stops, hidden tests that the agent never saw are written (overwriting any same-named files) and run. A case passes when those tests pass and the agent produced a diff.
3. The scorecard reports pass rate, turns, commands, duration, and LLM calls per tier. `tests/test_evals.py` drives the harness with a scripted LLM, so CI exercises it without API calls.

---

## 9. Future Architectural Evolutions

1. **Phase 5: Unified WorkspaceProvider & MicroVM Sandboxes**: Protocol abstraction supporting local Docker, Subprocess fallback, and cloud MicroVMs (Fly Machines / Firecracker / Modal).
2. **Phase 6: Interactive Human-in-the-Loop Steering**: Mid-flight steering while a run is in progress (follow-ups after a run finishes already exist), destructive command approvals, and terminal attach.
3. **Phase 7: Semantic Code Indexing & LSP Support**: Tree-sitter AST symbol graphs, vector embeddings for large repositories, and real-time diagnostic feedback.
