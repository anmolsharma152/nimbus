# Nimbus — Project Tasks & Milestone Roadmap Tracker

> **Tracking all delivered milestones, active development phases, operational checklists, and future roadmap capabilities for the Nimbus Autonomous Cloud Software Engineering Agent Platform.**

---

## 📊 Milestone Summary & Progress Dashboard

| Milestone Phase | Focus Area | Status | Key Deliverables |
| :--- | :--- | :---: | :--- |
| **Phase 0** | Foundation, Storage & Sandboxing | ✅ **Completed** | Asynchronous PostgreSQL persistence, Alembic migrations, Redis `arq` queue, Docker-mode resource limits (`1g` RAM, `2.0` CPU, `256` PIDs, `cap_drop ALL`). |
| **Phase 1** | Single-Agent Execution & Patching | ✅ **Completed** | 3-tier resilient LLM router (Gemini 3.6/3.7/3.5 $\to$ Groq 120B $\to$ OpenRouter), disk write enforcement, git diff capture, Next.js streaming terminal. |
| **Phase 2** | GitHub Workflow & Cloud Console | ✅ **Completed** | Branch isolation (`nimbus/task-<id>`), automated GitHub Draft PR dispatch, 100-repo selector, multi-cloud deployment (Render + Neon + Upstash + Vercel). |
| **Phase 3** | Identity & Access Control (AuthN/Z) | ✅ **Completed** | GitHub OAuth 2.0, HTTP-only JWT sessions, multi-tenant database scoping (`user_id`), dynamic repository proxy (`GET /api/repos`). |
| **Phase 4** | Credential Vault & Distributed Bus | ✅ **Completed** | Server-backed Fernet AES-256 BYOK vault (`UserCredential`), 4-step onboarding wizard (`/onboarding`), Redis Pub/Sub & Streams distributed event bus. |
| **Phase 5** | Visual Verification & Evals Harness | ✅ **Completed** | Binary base64 screenshot extraction, 3-tab inspector (Terminal, Patch Diff, Visual Preview + Lightbox), SWE benchmark evaluation suite (`eval_runner.py`). |
| **Hardening** | Security, Reliability & Delivery | ✅ **Completed** | Sign-in for repo tasks (no server token), protected-branch and force-with-lease push rules, access check + fork flow, follow-ups on the same task/branch/PR, CI quality gates. |
| **Phase 6** | Unified Workspace & MicroVMs | 📋 **Planned** | `WorkspaceProvider` protocol interface, cloud MicroVM sandboxes (Fly Machines / Modal / Firecracker), automated multi-cloud CI/CD deployment blueprints. |
| **Phase 7** | Interactive Human-in-the-Loop | 📋 **Planned** | Mid-flight user prompt injection, step-by-step destructive action approvals, interactive terminal attach over WebSocket. |
| **Phase 8** | Semantic Code Intelligence & LSP | 📋 **Planned** | Tree-sitter AST symbol graphs, vector embeddings for large repository indexing, real-time language server diagnostics. |

---

## ✅ Delivered Milestones

### Phase 0: Foundation, Persistence & Ephemeral Sandbox Hardening
- [x] **Asynchronous Persistence Layer**: SQLAlchemy 2.0 async engine with `asyncpg` connection pooling (`pool_size=20`, `max_overflow=10`, `pool_pre_ping=True`).
- [x] **Alembic Migrations**: Relational schema migrations for `users`, `user_credentials`, `tasks`, and `task_events`.
- [x] **Docker Sandbox Hardening**: cgroup limits in Docker mode (`mem_limit="1g"`, `nano_cpus=2_000_000_000`, `pids_limit=256`, `cap_drop=["ALL"]`, `security_opt=["no-new-privileges:true"]`). Production (Render) has no Docker daemon and uses SubprocessWorkspace, which has no resource caps.
- [x] **Execution Timeout Watchdog**: Per-command execution wrapper (`timeout 300 bash -c ...`) preventing runaway or hanging processes.
- [x] **Token-Safe Git**: Clone and push run outside the agent's user with the token passed via `GIT_CONFIG_*` env; the push replays the agent's patch onto a fresh clone.
- [x] **Pre-built Workspace Image**: Custom Dockerfile (`backend/Dockerfile.workspace`) with pre-installed build tools and runtime dependencies.

### Phase 1: Safe Single-Agent Reasoning & Patch Generation
- [x] **3-Tier Multi-LLM Reasoning Engine**: Resilient hierarchical fallback spanning Tier 1 (Intra-Gemini pool across `gemini-3.6-flash`, `gemini-3.7-flash`, `gemini-3.5-flash`), Tier 2 (Groq `openai/gpt-oss-120b`), and Tier 3 (OpenRouter `cohere/north-mini-code:free`).
- [x] **Context Window Optimization**: Groq token truncation (5,500 tokens) to stay within 8,000 TPM limit, and output length clipping (10,000 chars).
- [x] **Stall Watchdog & Jittered Backoff**: 5-minute timeout per turn with exponential retry on transient 429/503 provider errors.
- [x] **Disk Write Enforcement**: System prompt directives enforcing actual file writes on disk (`cat << 'EOF' > ...`) and unit testing before final summary.
- [x] **Automated Git Diff Extraction**: Reliable patch computation (`git add -N . && git diff HEAD`) and commit generation.
- [x] **Live Flight Recorder**: Real-time terminal output streaming with auto-scroll and UTC timestamp normalization.

### Phase 2: Multi-Tenant GitHub Workflow & Web UI
- [x] **Repository URL Normalization**: Robust parser supporting HTTPS, SSH, and `owner/repo` formats.
- [x] **Feature Branch Isolation**: Dynamic creation and checkout of dedicated task branches (`nimbus/task-<task_id>`).
- [x] **Automated Draft Pull Requests**: GitHub REST API client dispatching formatted markdown PRs with diff summaries.
- [x] **Glassmorphic Web Console**: Next.js 16 (React 19, Turbopack) UI with repository selector, user/org switcher, prompt presets, and copy logs.
- [x] **Task Lifecycle Controls**: Task cancellation (`POST /api/tasks/{id}/cancel`) and task retry (`POST /api/tasks/{id}/retry`) endpoints.
- [x] **Production Multi-Service Deployment**: Live cloud deployment across Render, Neon, Upstash, and Vercel (`https://nimbusagent.vercel.app`).

### Phase 3: Identity & Access Control (AuthN / AuthZ)
- [x] **GitHub OAuth 2.0 Flow**: Complete web flow (`/api/auth/github/login`, `/api/auth/github/callback`, `/api/auth/me`, `/api/auth/logout`).
- [x] **Secure JWT Session Management**: HTTP-only session cookies with Fernet AES-256 token encryption at rest.
- [x] **Multi-Tenant Scoping**: All task endpoints (`/api/tasks/*`) and queries strictly isolated to authenticated `user_id`.
- [x] **Dynamic Repository Discovery**: `GET /api/repos` endpoint querying up to 100 repositories from the user's authenticated GitHub profile.
- [x] **Frontend Authentication Context**: Next.js `AuthContext.tsx`, dedicated `/login` page, and user avatar navigation badge.

### Phase 4: User Credential Vault & Distributed Event Bus
- [x] **Fernet AES-256 Credential Vault**: `UserCredential` table for per-user token and BYOK LLM key storage (`gemini`, `groq`, `openrouter`, `github_pat`).
- [x] **Interactive Onboarding Wizard**: 4-step onboarding flow at `/onboarding` (Profile $\to$ Repo Discovery $\to$ BYOK Keys $\to$ Starter Task).
- [x] **Dedicated Settings Dashboard**: Server-backed `/settings` view eliminating client-side `localStorage` credential storage.
- [x] **User Git Attribution**: Sandbox configured with `git config user.name/email` to personal developer profile, and PRs authored under personal GitHub identity.
- [x] **Distributed Redis Event Bus**: `RedisEventBus` with Pub/Sub channels and Streams for multi-replica API event fan-out.
- [x] **Authenticated WebSocket Gateway**: Token-authenticated WebSocket handshake with 1008 policy-violation protection.
- [x] **Rate Limiting & Concurrency Quotas**: Sliding window and tier-based concurrency control (`ratelimit.py`) preventing sandbox monopolization.

### Phase 5: Browser Automation, Visual Verification & Benchmark Evals
- [x] **Binary Image Extraction**: `UnifiedWorkspace.aget_file_base64()` extracting `.png` artifacts from Docker and subprocess environments.
- [x] **Reasoning Loop Screenshot Capture**: Agent support for emitting `{"command": "...", "screenshot": "preview.png", "caption": "..."}`.
- [x] **Visual Snapshot API**: `GET /api/tasks/{task_id}/screenshots` returning structured visual snapshot artifacts.
- [x] **3-Tab Task Inspector**: Terminal Flight Recorder, Patch Diff Viewer, and Visual Preview Gallery with high-resolution Lightbox modal.
- [x] **Autonomous SWE Evaluation Suite**: Benchmark runner (`backend/evals/eval_runner.py`) executing synthetic test cases and live filesystem workspace validations.

### Hardening (2026-10)
- [x] **Security hotfixes**: Closed the auth bypass, scoped task APIs to their owner, authenticated internal worker events.
- [x] **Workspace lifecycle**: 30-minute task time limit; workspaces are torn down reliably, and a reaper cleans up after crashes.
- [x] **Secrets**: `SecretStr` settings; tests never load the real `.env`.
- [x] **Sandbox isolation**: Per-task UID and scrubbed env in SubprocessWorkspace; GitHub token kept out of the agent's reach.
- [x] **Streams & observability**: WebSocket streams survive disconnects; structured logs with request/task context; eval harness runs the real agent loop.
- [x] **Same-site auth**: Session cookie kept first-party via the `/api` proxy; WebSockets use 60 s stream tickets.
- [x] **CI quality gates**: GitHub Actions running ruff, pytest with a 78% coverage floor, eslint, `tsc`, vitest and `next build`.
- [x] **Anonymous task guard**: Repo tasks require sign-in, the server `GITHUB_TOKEN` is removed, protected branch names are rejected (422), first pushes only create new branches, and signed-out visitors share an hourly cap (`ANON_TASKS_PER_HOUR`).
- [x] **Repo permissions**: Access is checked before running; without write access Nimbus pushes to a fork and opens the PR from it; PRs target the repo's default branch.
- [x] **Follow-ups**: `POST /api/tasks/{id}/messages` continues the same task, branch and PR from the task's base commit and changes so far; retry keeps the branch and PR.

---

## 🎯 Next Milestone: Phase 6

### Phase 6: Unified Workspace Provider & Cloud MicroVM Sandboxes
- [ ] **`WorkspaceProvider` Protocol**: Formalize Python `typing.Protocol` / `abc.ABC` interface for all sandbox engines (`DockerWorkspace`, `SubprocessWorkspace`, `MicroVMWorkspace`).
- [ ] **Cloud MicroVM Adapter**: Prototype Firecracker / Fly Machines / Modal backend for serverless on-demand containerless execution.
- [x] **Automated CI Workflows**: `.github/workflows/ci.yml` (backend lint/tests/coverage, frontend lint/typecheck/tests/build).
- [ ] **Resource & network limits in production**: SubprocessWorkspace has neither today.
- [ ] **Infrastructure-as-Code & Blueprints**: Refined `render.yaml` and Railway deployment templates with managed secret injection.

---

## 📋 Future Milestone Roadmap

### Phase 7: Interactive Human-in-the-Loop & Execution Controls
- [ ] **Mid-Flight Steering**: Allow users to inject corrections while the agent loop is running (follow-ups after a run finishes already work).
- [ ] **Policy & Destructive Action Approvals**: Pause execution and request user approval for high-risk operations (e.g. database schema drops, mass file deletions, non-standard port listeners).
- [ ] **Interactive Terminal Gateway**: Provide an optional real-time xterm.js interactive shell attach for developer manual intervention.

### Phase 8: Semantic Code Intelligence & Repository Indexing
- [ ] **Tree-sitter AST Symbol Graphing**: Generate project symbol definitions, function signatures, and call hierarchies to enhance agent reasoning.
- [ ] **Sub-Repository Vector Embeddings**: Pre-index large codebases (>50k LOC) with hybrid keyword + semantic search for rapid file targeting.
- [ ] **LSP Diagnostics Integration**: Ingest real-time language server diagnostics (Pyright, TypeScript Language Server) to catch type errors before test execution.

---

## 🛠️ Operational & Technical Debt Checklist

- [x] Eliminate hardcoded user fallbacks and purge client-side API key caching in `localStorage`.
- [x] Normalize all database timestamps to ISO-8601 UTC with explicit `Z` suffix.
- [x] Graceful cleanup of idle WebSocket connections and Redis pub/sub listeners.
- [x] Remove legacy keep-alive workflows in favor of UptimeRobot monitoring.
- [ ] Optimize pre-built Docker workspace image size (`backend/Dockerfile.workspace`).
- [ ] Add Prometheus / OpenTelemetry telemetry metrics for LLM token usage and task execution duration.

---

## 🧪 Test Suite & Verification

- **Backend**: `cd backend && uv run pytest --cov` (all mocked; no DB, Redis, Docker or LLM calls). CI fails below 78% coverage.
- **Frontend**: `npm run lint`, `npm run typecheck`, `npm test` (vitest), `npm run build`.
- **Agent eval**: `uv run python evals/eval_runner.py` runs the real agent loop on fixture repos and **uses your LLM keys**; `tests/test_evals.py` covers the harness with a scripted LLM.
