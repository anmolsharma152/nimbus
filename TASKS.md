# Nimbus — Project Tasks & Milestone Tracker

## ✅ Completed Milestones

### Phase 0: Foundation & Sandbox Hardening
- [x] Ephemeral Docker sandbox lifecycle with hard resource limits (`mem_limit="1g"`, `nano_cpus=2_000_000_000`, `pids_limit=256`, `cap_drop=["ALL"]`, `security_opt=["no-new-privileges:true"]`)
- [x] Command timeout execution wrapper (`timeout 300 bash -c ...`) preventing runaway hanging processes
- [x] Pre-built sandbox workspace container (`backend/Dockerfile.workspace`)
- [x] Sanitized shell inputs with `shlex.quote()` and transient header-based Git authentication (`http.extraheader`)
- [x] Non-blocking asynchronous Docker execution wrappers (`asyncio.to_thread`)
- [x] PostgreSQL connection pool tuning (`pool_size=20`, `max_overflow=10`, `pool_pre_ping=True`)
- [x] Alembic database schema migrations for task persistence and append-only event streams

### Phase 1: Safe Single-Agent Execution & Patch Generation
- [x] Ephemeral container creation, provisioning, execution, diff extraction, and cleanup
- [x] Multi-tier resilient LLM reasoning loop (`gemini-3.6/3.7/3.5-flash` → `openai/gpt-oss-120b` → `cohere/north-mini-code:free`)
- [x] Output length truncation (10,000 chars) preserving model context window
- [x] 5-minute stall watchdog and exponential backoff retry on 429/503 provider errors
- [x] Automated git diff extraction (`git add -N . && git diff HEAD`) and commit handling
- [x] Next.js 16 Web UI with real-time WebSocket terminal flight recording, auto-scroll, and copy logs

### Phase 2: Multi-Tenant GitHub Workflow & UI Overhaul
- [x] GitHub repository URL parser supporting HTTPS, SSH, and `owner/repo` formats
- [x] Automated feature branch creation (`nimbus/task-<task_id>`)
- [x] Automated Draft Pull Request creation via GitHub REST API with formatted markdown summary
- [x] Complete 100-repository dynamic selector, user/org switcher, prompt presets, split-view inspector, and SVG vector icons
- [x] Task cancellation (`POST /api/tasks/{task_id}/cancel`) and task retry (`POST /api/tasks/{task_id}/retry`) endpoints
- [x] Multi-service cloud deployment live on Render, Neon, Upstash, and Vercel

---

## 🎯 Active & Upcoming Milestones

### Phase 3: Identity & Access Control (AuthN / AuthZ)
- [x] Add `User` model (`id`, `github_id`, `username`, `display_name`, `email`, `avatar_url`, `github_token`) in `models.py`
- [x] Add `user_id` foreign key on `Task` model with Alembic database migration (`b2c3d4e5f6a7`)
- [x] Implement GitHub OAuth 2.0 flow in `backend/app/auth.py` (`/api/auth/github/login`, `/api/auth/github/callback`, `/api/auth/me`, `/api/auth/logout`)
- [x] Implement Fernet AES-256 secret encryption and secure HTTP-only JWT sessions in `backend/app/security.py`
- [x] Scope all task REST endpoints (`/api/tasks/*`) to user identity and multi-tenant isolation
- [x] Implement dynamic user repository proxy (`GET /api/repos`) using authenticated user's GitHub OAuth token
- [x] Build Next.js `AuthContext.tsx` and dedicated `/login` page with 1-click GitHub Sign-In
- [x] Update frontend header, task creation form, and sidebar with user avatar, username, and sign-out controls

### Phase 2: Onboarding & User Credential Vault
- [x] Add Fernet-encrypted `UserCredential` model for per-user token and BYOK key storage (`c3d4e5f6a7b8`)
- [x] Build 4-step interactive onboarding wizard (`/onboarding`): Profile confirmation → Repo discovery → BYOK key setup → Instant starter task
- [x] Build server-backed `/settings` dashboard and eliminate client-side localStorage credentials
- [x] Configure sandbox git author identity (`git config user.name/email`) using authenticated user's profile
- [x] Create Pull Requests and push branches strictly authored by the user's personal GitHub account

### Phase 3: Scaling & Event Streaming
- [x] Implement distributed Redis Event Bus (`backend/app/events.py`) with Pub/Sub & Streams fan-out for multi-replica API deployments
- [x] Implement authenticated WebSocket handshakes (`/ws/tasks/{id}?token=...`) with user authorization verification
- [x] Add per-user rate limiting and concurrency quotas (`backend/app/ratelimit.py`) preventing sandbox monopolization

### Phase 4: Browser Automation & Visual Verification
- [x] Add binary screenshot extraction (`get_file_base64` / `aget_file_base64`) to `DockerWorkspace` and `SubprocessWorkspace`
- [x] Capture visual screenshot artifacts and stream to frontend inspector via `GET /api/tasks/{id}/screenshots` and WebSocket stream
- [x] Add "Visual Preview" gallery tab alongside terminal flight recorder and patch diff viewer with full-screen lightbox modal

---

## 🎯 Active & Upcoming Milestones

### Phase 5: Sandbox Provider Abstraction & Production Hardening
- [ ] Define `WorkspaceProvider` protocol interface (`DockerWorkspace`, `SubprocessWorkspace`, `MicroVMWorkspace`)
- [ ] Production deployment automation and environment blueprint updates
- [ ] Full documentation and architecture diagram synchronization

---

## 🧪 Test & Build Verification
- [x] 46/46 pytest backend unit & integration tests passing (`uv run pytest`)
- [x] Clean Next.js 16 production build with Turbopack (`npm run build`)
- [x] Clean git working tree on `main`

