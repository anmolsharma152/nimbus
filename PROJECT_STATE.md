# Project State

## Project Summary

Nimbus is a Devin-style cloud software-engineering agent: users delegate coding tasks from a web UI, a control-plane agent works in an isolated, disposable cloud workspace, and returns a reviewable branch/PR and tested patch. Intent, architecture, and delivery plan live in `docs/architecture.md`, `docs/roadmap.md`, and `docs/security.md`.

## Current Development Phase

Phase 2 (GitHub Integration, Repository Cloning & Draft PR Workflow) completed with full test coverage and evals suite.

## Implemented Features

- **Architecture & System Design**:
  - Full end-to-end Mermaid sequence diagram, trust boundaries chart, and task/event lifecycle state machine in [docs/architecture.md](docs/architecture.md).
- **Task Lifecycle & Schema**:
  - PostgreSQL persistence with Alembic migrations (`tasks`, `task_events`), supporting `repo_url`, `git_branch`, `pr_url`, `patch_diff`, and status enum (`pending`, `running`, `completed`, `failed`, `cancelled`).
- **Event Stream & WebSocket Gateway**:
  - Append-only `TaskEvent` rows, WebSocket streaming (`/ws/tasks/{id}`) with historical replay on connect.
- **Worker & Queue**:
  - `arq` worker consuming jobs over Redis and orchestrating the Gemini agent loop.
- **Docker Workspace Container**:
  - Ephemeral container creation, git safe directory setup, build tools installation.
  - Automatic repository cloning (authenticated via GitHub token if provided).
  - Feature branch creation (`nimbus/task-<task_id>`).
  - Git identity configuration (`Nimbus Agent <agent@nimbus.ai>`).
  - Diff extraction (`get_diff`) and commit helper.
- **GitHub Integration (`backend/app/github_client.py`)**:
  - GitHub repository parsing.
  - Draft Pull Request creation via GitHub REST API.
  - Feature branch pushing.
- **Frontend UI (`frontend/`)**:
  - Dark glassmorphism task submission interface with prompt and repository URL inputs.
  - Task execution page with live log/command stream, auto-scroll, branch indicator, Draft PR button, and patch diff inspector.
- **Control Plane & Async Hardening**:
  - Pydantic response models, HTTP 404 exception handling, task cancellation endpoint (`POST /api/tasks/{id}/cancel`).
  - Production connection pooling (`pool_size=20`, `max_overflow=10`, `pool_pre_ping=True`).
  - True non-blocking asynchronous workspace operations (`asetup`, `aexecute_command`, `aget_diff`, `acommit_changes`, `apush_branch`, `acleanup`) and async Gemini client (`client.aio.chats`).
- **Testing & Evals**:
  - 17 comprehensive unit & integration tests covering REST API endpoints, cancellation flow, Workspace isolation, Worker agent loop, GitHub client, and schemas (`uv run pytest` -> 17/17 passed).
  - Benchmark evaluation runner (`backend/evals/eval_runner.py`) generating performance scorecards.

## Verification & Build Status

- Backend: 17/17 tests passing (`uv run pytest`).
- Frontend: Next.js 16 build passing with zero errors (`npm run build`).
- Git: Clean working tree on `main`.
