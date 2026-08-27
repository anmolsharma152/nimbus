# Delivery Roadmap

## Completed Milestones (Phases 0–2 Prototype)

### Phase 0 — Foundation & Durable State ✅
- Asynchronous PostgreSQL persistence (`Task`, `TaskEvent`), Alembic migrations, Redis `arq` background queue, and WebSocket streaming gateway.
- Ephemeral Docker sandbox lifecycle with strict Linux cgroup limits (`1g` RAM, `2.0` CPUs, `256` PIDs, `cap_drop=["ALL"]`, `security_opt=["no-new-privileges:true"]`, `300s` timeout).

### Phase 1 — Safe Single-Agent Execution & Patching ✅
- 3-tier resilient multi-LLM reasoning loop (`gemini-3.6/3.7/3.5-flash` → `openai/gpt-oss-120b` → `cohere/north-mini-code:free`) with jittered backoff on 429/503 spikes.
- Automated git diff extraction (`git add -N . && git diff HEAD`) and commit handling.
- Next.js 16 Web UI with live streaming flight recorder terminal, auto-scroll, and historical event replay.

### Phase 2 — GitHub Workflow & Cloud Deployment ✅
- Feature branch creation (`nimbus/task-<task_id>`) and automated Draft Pull Request generation via GitHub REST API.
- 100-repository dynamic selector, user/org switcher, prompt presets, split-view inspector, and SVG vector icons.
- Cloud deployment live on Render (backend/worker), Neon (PostgreSQL 16), Upstash (Redis 7), and Vercel (frontend).

---

## Active & Upcoming Delivery Phases

### Phase 1 — Identity & Access Control (AuthN / AuthZ)
- Implement GitHub OAuth 2.0 flow (`/api/auth/github/login`, `/api/auth/github/callback`, `/api/auth/me`).
- Secure HTTP-only JWT sessions and `User` database model.
- Strict multi-tenant isolation: all task queries and WebSocket streams scoped to `current_user.id`.
- Dynamic repository proxy (`GET /api/repos`) querying user's authenticated GitHub account.
- Frontend `/login` page with 1-click GitHub Sign-In and user profile in navigation.

**Exit criterion:** Unauthenticated users cannot view or create tasks. Every task and repository list is strictly scoped to the authenticated user.

### Phase 2 — Onboarding & User Credential Vault
- Fernet-encrypted `UserCredential` table storing per-user tokens and optional BYOK API keys.
- 4-step interactive onboarding wizard (`/onboarding`) guiding users through profile sync, repo selection, model keys, and first task launch.
- Server-backed `/settings` dashboard eliminating client-side `localStorage` credentials.
- Sandbox git author attribution (`git config user.name/email`) and PR dispatch authored by the user's personal GitHub identity.

**Exit criterion:** A new user completes onboarding, submits a task, and receives a Pull Request on GitHub authored by their personal account.

### Phase 3 — Scaling & Event Streaming
- Transition from HTTP localhost event broadcast to Redis Streams / Pub-Sub event fan-out for horizontal API clustering.
- Authenticated WebSocket handshakes with token validation.
- Per-user rate limiting and concurrency quotas.

**Exit criterion:** Multiple API replicas receive and broadcast live events across user WebSocket connections seamlessly.

### Phase 4 — Browser Automation & Visual Verification
- Embed Playwright in workspace sandbox container for automated web application testing.
- Capture screenshot artifacts and stream them to the frontend inspector's "Visual Preview" tab.

**Exit criterion:** The agent validates a web frontend modification and provides a verified screenshot artifact.

### Phase 5 — Sandbox Provider Abstraction & Production Hardening
- Pluggable `WorkspaceProvider` interface supporting local Docker, fallback Subprocess, and cloud MicroVMs (Fly Machines / Modal).
- Automated CI/CD pipelines and deployment blueprint configurations.
- Documentation and architecture diagram synchronization.

**Exit criterion:** Seamless self-service deployment across cloud providers with automated test verification.

