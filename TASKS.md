# Nimbus — Project Tasks & Milestone Tracker

## Phase 0: Foundation & Sandbox Hardening
- [x] Add resource constraints to `containers.run()` (mem_limit, nano_cpus, pids_limit, dropped capabilities, no-new-privileges)
- [x] Add command timeout execution wrapper to prevent hanging processes
- [x] Create pre-built sandbox workspace container (`backend/Dockerfile.workspace`)
- [x] Sanitize shell commands with `shlex.quote()` and transient header-based Git auth
- [x] Implement non-blocking async Docker execution wrappers (`asyncio.to_thread`)
- [x] PostgreSQL connection pool tuning (`pool_size=20`, `max_overflow=10`, `pool_pre_ping=True`)
- [x] Alembic database schema migrations for task persistence and event streams

## Phase 1: Safe Single-Agent Execution & Patch Generation
- [x] Ephemeral Docker container lifecycle (create, provision, execute, diff, cleanup)
- [x] Async Gemini 2.5 agent loop with JSON command protocol and error self-correction
- [x] Output length truncation (10,000 chars) to preserve context window
- [x] Automated git diff extraction (`git add -N . && git diff HEAD`) and commit handling
- [x] Next.js 16 Web UI with real-time WebSocket terminal log stream and auto-scroll

## Phase 2: Multi-Tenant GitHub Workflow
- [x] GitHub repository URL parser supporting HTTPS, SSH, and `owner/repo` formats
- [x] Feature branch creation (`nimbus/task-<task_id>`)
- [x] Automated Draft Pull Request creation via GitHub REST API with formatted markdown summary
- [x] Frontend UI inputs for prompt and optional target repository URL
- [x] Clickable Draft PR link and collapsible patch diff viewer in UI

## Phase 3: Product-Grade Scalability & Visibility
- [x] Fast HTTP 404 exception handling and Pydantic response models
- [x] Task cancellation endpoint (`POST /api/tasks/{task_id}/cancel`) and agent loop interruption
- [x] ConnectionManager memory leak cleanup on WebSocket disconnection
- [x] Extracted environment variables (`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`) in frontend
- [ ] Redis Pub/Sub multi-instance event bus integration
- [ ] MicroVM sandbox provider interface (Firecracker / Modal / Fly Machines)

## Phase 4: Browser Automation & Production Cloud Deployment
- [ ] Playwright browser integration for visual web app verification
- [ ] Automated visual screenshot artifact capture
- [ ] Multi-service cloud deployment (Render + Neon Postgres + Upstash Redis + Vercel)

## Test & Build Verification
- [x] 17/17 pytest backend unit & integration tests passing
- [x] Clean Next.js 16 production build with Turbopack
- [x] Git working tree clean on `main`
