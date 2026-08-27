# Session Handoff

## Current Work Session (August 27, 2026)

Nimbus has evolved from early prototypes into a fully functional, cloud-deployed autonomous software engineering agent platform. The system features a trusted FastAPI control plane with asynchronous `asyncpg` connection pooling, an `arq` background worker driving a 3-tier multi-LLM reasoning loop (Gemini 3.6/3.7/3.5, Groq `openai/gpt-oss-120b`, OpenRouter `cohere/north-mini-code:free`), ephemeral Docker sandbox isolation with Linux cgroups/resource caps, live WebSocket flight recording with historical event replay, and automated GitHub Draft PR dispatch.

---

## What Was Completed

- **Multi-Tier LLM Reasoning Loop (`backend/app/llm.py`)**:
  - 3-tier automatic failover hierarchy: Tier 1 (Intra-Gemini pool with 3.6-flash, 3.7-flash, 3.5-flash) → Tier 2 (Groq GPT-OSS 120B with context window truncation) → Tier 3 (OpenRouter free tier).
  - Exponential backoff with jitter for transient 429/503 rate limits and a 5-minute stall watchdog.
  - Enforced disk file write verification before agent final summaries.
- **Docker Sandbox Hardening (`backend/app/workspace.py`)**:
  - Ephemeral container lifecycle with `mem_limit="1g"`, `nano_cpus=2_000_000_000`, `pids_limit=256`, `cap_drop=["ALL"]`, `security_opt=["no-new-privileges:true"]`, and 300s execution timeouts.
  - Non-blocking `asyncio.to_thread` execution wrappers and transient header Git authentication (`http.extraheader`) keeping tokens out of `.git/config`.
- **Control Plane & WebSocket Replay (`backend/app/main.py`)**:
  - REST endpoints for task creation, status inspection, cancellation (`POST /api/tasks/{id}/cancel`), and retries (`POST /api/tasks/{id}/retry`).
  - Memory leak prevention in `ConnectionManager` and UTC timestamp normalization.
- **Frontend Modernization (`frontend/`)**:
  - Next.js 16 (React 19, Turbopack) dark glassmorphic console with clean White Cloud branding.
  - Full 100-repository dynamic selector, user/org switcher, prompt presets, split-view task inspector, and copy logs.
  - Settings Modal for custom API key configuration.
  - Rich OpenGraph/Twitter card SEO metadata and JSON-LD schema.
- **Testing & Verification**:
  - **46/46 Pytest backend tests passing** (`test_api`, `test_auth`, `test_browser`, `test_credentials`, `test_evals`, `test_github_client`, `test_llm`, `test_scaling`, `test_worker`, `test_workspace`).
  - **Next.js 16 production build passing with 0 errors** across all static/dynamic routes (`/`, `/login`, `/onboarding`, `/settings`, `/tasks/[id]`, `/about`, `/architecture`, `/security`).
  - Deployed live on Render + Neon PostgreSQL + Upstash Redis + Vercel (`https://nimbusagent.vercel.app`).

---

## Immediate Next Milestone: Multi-Tenant Platform & Onboarding

Transform Nimbus from a single-tenant prototype with hardcoded GitHub username/server tokens into a **user-agnostic, multi-tenant consumer platform**:

1. **Phase 1: Identity & Access Control**:
   - GitHub OAuth 2.0 flow (`/api/auth/github/login`, `/api/auth/github/callback`, `/api/auth/me`).
   - Secure HTTP-only JWT sessions.
   - `User` model (`id`, `github_id`, `username`, `email`, `avatar_url`) and `user_id` foreign key on `tasks`.
   - User-scoped task access and live repository discovery (`GET /api/repos` via user's OAuth token).
2. **Phase 2: Onboarding & Credential Vault**:
   - Fernet-encrypted `UserCredential` table for per-user token and BYOK LLM key storage.
   - 4-step onboarding wizard (`/onboarding`).
   - User-attributed git commits (`git config user.name/email`) and PR authoring under the user's GitHub identity.
   - Elimination of localStorage credentials in favor of server-backed vault.
3. **Phase 3: Event Scaling & WebSocket Auth**:
   - Redis Streams / Pub-Sub event fan-out across multiple API instances.
   - Authenticated WebSocket handshakes.

---

## Key Files Reference

- `backend/app/main.py`: FastAPI control plane routes & WebSocket connection manager.
- `backend/app/worker.py`: `arq` worker orchestrating agent lifecycle and git operations.
- `backend/app/workspace.py`: Ephemeral Docker and Subprocess workspace sandboxes.
- `backend/app/llm.py`: 3-tier resilient LLM chat session with failover routing.
- `backend/app/github_client.py`: GitHub REST API client for Draft PR generation.
- `frontend/src/app/page.tsx`: Main task submission console.
- `frontend/src/app/tasks/[id]/page.tsx`: Real-time streaming terminal & patch diff inspector.
- `TASKS.md` / `docs/roadmap.md`: Sequenced multi-phase roadmap and execution checklist.
