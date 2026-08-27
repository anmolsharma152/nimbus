# Project State

## Project Summary

Nimbus is a Devin-style cloud software-engineering agent platform: users delegate coding tasks from a web UI, while a trusted control-plane agent orchestrates an isolated, ephemeral cloud sandbox to inspect repositories, modify code, execute test suites, capture tested patches, and open GitHub Pull Requests with real-time flight recording. Intent, architecture, and delivery plan live in `docs/architecture.md`, `docs/roadmap.md`, `docs/security.md`, and `docs/cloud_deployment.md`.

---

## Current Development Phase

**Phase 4 (Browser Automation & Visual Verification) Completed. Transitioning to Phase 5: Sandbox Provider Abstraction & Production Hardening (Unified Workspace Provider protocol, multi-backend microVM integration, and deployment blueprints).**

---

## Implemented Features

- **Browser Automation & Visual Verification (Screenshot Stream & Lightbox)**:
  - `UnifiedWorkspace.aget_file_base64()` binary image extractor for Docker and subprocess environments.
  - Live screenshot capturing via `{"screenshot": "...", "caption": "..."}` in worker reasoning loops.
  - Endpoint `GET /api/tasks/{task_id}/screenshots` returning structured visual snapshot artifacts.
  - 3-Tab Task Inspector UI with **Terminal Flight Recorder**, **Patch Diff**, and **Visual Preview Gallery** with high-res Lightbox modal.
- **Distributed Event Streaming & Rate Limiting (Redis Pub/Sub & Quotas)**:
  - `RedisEventBus` ([`backend/app/events.py`](file:///home/omarchy/Projects/Nimbus/backend/app/events.py)) with dual Redis Pub/Sub channels and Streams for multi-replica event fan-out.
  - Authenticated WebSocket gateway ([`backend/app/main.py`](file:///home/omarchy/Projects/Nimbus/backend/app/main.py)) with JWT token verification and 1008 policy-violation protection for unauthorized streams.
  - Per-user concurrency quotas and sliding window rate limiting ([`backend/app/ratelimit.py`](file:///home/omarchy/Projects/Nimbus/backend/app/ratelimit.py)) preventing sandbox monopolization.
- **Onboarding & User Credential Vault (Fernet Vault & BYOK Routing)**:
  - `UserCredential` encrypted table storing personal API keys (`gemini`, `groq`, `openrouter`, `github_pat`) encrypted with Fernet AES-256 at rest.
  - Endpoints `GET /api/settings/credentials`, `PUT /api/settings/credentials/{provider}`, `DELETE /api/settings/credentials/{provider}`, `POST /api/users/onboarding-complete`.
  - 4-step interactive onboarding wizard at `/onboarding` (Profile $\to$ Repo Discovery $\to$ BYOK Keys $\to$ Instant Starter Launch).
  - Dedicated `/settings` dashboard for managing vault keys and account integrations.
  - Sandbox git author attribution (`git config user.name/email`) configured to developer profile, and PR author attribution (`@username`) on GitHub.
  - BYOK key injection into `LLMChatSession` and worker agent loops.
- **Identity & Access Control (AuthN / AuthZ)**:
  - Database `User` model with GitHub OAuth 2.0 flow (`/api/auth/github/login`, `/api/auth/github/callback`, `/api/auth/me`, `/api/auth/logout`).
  - Secure HTTP-only JWT session management and Fernet AES-256 secret token encryption at rest.
  - Multi-tenant isolation across all task endpoints (`/api/tasks/*`) and dynamic repository proxy (`GET /api/repos`).
  - Frontend `AuthContext.tsx`, dedicated `/login` page, and user profile badges in navigation.
- **Multi-Tier LLM Architecture (`backend/app/llm.py`)**:
  - 3-tier resilient failover router: Tier 1 (Intra-Gemini pool across `gemini-3.6-flash`, `gemini-3.7-flash`, `gemini-3.5-flash`) → Tier 2 (Groq `openai/gpt-oss-120b`) → Tier 3 (OpenRouter `cohere/north-mini-code:free`).
  - Exponential backoff with jitter on 429/503 spikes, 5-minute stall watchdog, and Groq context window truncation.
- **Docker Sandbox Hardening & Isolation (`backend/app/workspace.py`)**:
  - Ephemeral container lifecycle with strict cgroups: `mem_limit="1g"`, `nano_cpus=2_000_000_000`, `pids_limit=256`, `cap_drop=["ALL"]`, `security_opt=["no-new-privileges:true"]`.
  - Non-blocking `asyncio.to_thread` wrappers and transient header-based Git authentication (`http.extraheader`).
  - Dual workspace engine: `DockerWorkspace` for local/cloud containers and fallback `SubprocessWorkspace` for environments without nested Docker daemons.
- **Control Plane & Durable Event Sourcing (`backend/app/main.py`)**:
  - Asynchronous PostgreSQL persistence via `asyncpg` connection pooling (`pool_size=20`, `max_overflow=10`).
  - Append-only `TaskEvent` stream with WebSocket streaming (`/ws/tasks/{id}`) and instant historical replay on connect.
  - Task cancellation (`POST /api/tasks/{id}/cancel`), task retries (`POST /api/tasks/{id}/retry`), task deletion, and Pydantic response models.
- **Frontend Console & UI/UX (`frontend/`)**:
  - Next.js 16 (App Router, Turbopack) dark glassmorphic console with clean White Cloud identity.
  - Complete 100-repository dynamic selector, user/org switcher, prompt presets, split-view task inspector, copy logs, and SVG icons.
  - Dedicated `/login`, `/onboarding`, `/settings`, `/architecture`, `/security`, and `/about` pages with rich OpenGraph/Twitter SEO metadata and JSON-LD schema.
- **Cloud Infrastructure & Deployment**:
  - Multi-service deployment across Render (FastAPI + arq worker), Neon (PostgreSQL 16), Upstash (Redis 7), and Vercel (Next.js 16 frontend at `https://nimbusagent.vercel.app`).

---

## Active Milestone & Next Tasks

1. **Phase 5: Sandbox Provider Abstraction & Production Hardening**:
   - `WorkspaceProvider` protocol interface (`DockerWorkspace`, `SubprocessWorkspace`, `MicroVMWorkspace`).
   - Production deployment automation and environment blueprint updates.
   - Full documentation and architecture diagram synchronization.

---

## Verification & Build Status

- **Backend Test Suite**: **46/46 tests passing** (`uv run pytest`).
- **Frontend Build**: Next.js 16 Turbopack build passing with **0 errors** (`npm run build`).
- **Git Working Tree**: Clean on `main`, synchronized with `origin/main`.

