# Nimbus: Cloud Production Deployment Guide

This guide walks through deploying the complete Nimbus autonomous agent platform to production across **Vercel** (Frontend), **Render / Railway** (Backend Control Plane & arq Worker), and managed **PostgreSQL & Redis**.

---

## Architecture Overview in Production

```
                                  [ User Browser ]
                                         │
                                         ▼
                     [ Frontend: Vercel (Next.js 16 Edge) ]
                                         │
                     ┌───────────────────┴───────────────────┐
                     │ HTTPS REST Request                    │ WSS Real-Time Logs
                     ▼                                       ▼
             [ Backend: Render / Railway Web Service (FastAPI) ]
                     │                                       │
     Postgres Async  │                       Job Queue /     │
     Connection Pool │                       Pub-Sub Channel │
                     ▼                                       ▼
    [ Database: Neon / Supabase ]                  [ Cache: Upstash Redis ]
         (PostgreSQL 16)                                (Managed TLS)
                     ▲                                       ▲
                     │ State Updates                         │ Dequeue Tasks
                     │                                       │
             [ Worker: Render / Railway Background Worker (arq) ]
                                     │
                                     ▼
      [ Ephemeral workspaces: SubprocessWorkspace on Render (no Docker daemon) ]
```

---

## Deployment Pathway 1: 1-Click Render Blueprint (Recommended)

Render provisions the backend from the included [`render.yaml`](../render.yaml): one Docker web service that runs both the API and the `arq` worker, plus a PostgreSQL database. Redis is not in the blueprint; use Upstash (see below) and paste its URL.

### Steps:
1. Log in to your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** → **Blueprint**.
3. Connect your GitHub repository: `anmolsharma152/nimbus`.
4. Render will detect [`render.yaml`](../render.yaml) and configure:
   * **`nimbus-api`**: `backend/entrypoint.sh` runs `alembic upgrade head`, starts the `arq` worker in the background, then Uvicorn.
   * **`nimbus-db`** (PostgreSQL)
5. Fill in the prompted values, then add the rest under the service's **Environment** tab:
   * `REDIS_URL`: your Upstash `rediss://` URL.
   * `GEMINI_API_KEY` (and/or `GROQ_API_KEY`, `OPENROUTER_API_KEY`): at least one LLM key, unless every user brings their own.
   * `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`: the GitHub OAuth app. Sign-in is required for repo tasks.
   * `JWT_SECRET_KEY`: a long random value. It also derives the key that encrypts stored user credentials, so changing it later makes them unreadable.
   * Optional: `ANON_TASKS_PER_HOUR` (default 10), the hourly task budget shared by signed-out visitors.
   * There is no server-wide GitHub token. If an old `GITHUB_TOKEN` variable is still set, it is ignored and can be deleted.
6. Click **Apply**.
7. Copy your public `nimbus-api` URL (e.g., `https://nimbus-api-l32h.onrender.com`).

---

## Deployment Pathway 2: Serverless Stack (Neon + Upstash + Vercel)

If you prefer serverless infrastructure with generous zero-cost free tiers:

### 1. Database (Neon Postgres)
1. Create a free project on [Neon.tech](https://neon.tech).
2. Copy your connection string (`postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require`).
3. Set this as `DATABASE_URL` (our backend automatically normalizes it to use `asyncpg`).

### 2. Queue (Upstash Redis)
1. Create a free database on [Upstash.com](https://upstash.com).
2. Copy the standard Redis connection string: `rediss://default:password@xyz.upstash.io:6379`.
3. Set this as `REDIS_URL`.

### 3. Backend (Render or Railway)
1. Create a Web Service pointing to `backend/Dockerfile`.
2. Add environment variables: `DATABASE_URL`, `REDIS_URL`, an LLM key, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `JWT_SECRET_KEY`, `FRONTEND_URL`, `OAUTH_REDIRECT_BASE_URL`.
3. Start command: `/bin/bash /app/entrypoint.sh`.

---

## Deploying the Frontend to Vercel

Once your backend is live and you have your public API URL (e.g. `https://nimbus-api-l32h.onrender.com`):

### Steps:
1. Open [vercel.com/new](https://vercel.com/new).
2. Select your repository: **`anmolsharma152/nimbus`**.
3. Set the **Root Directory** to: `frontend`.
4. In the **Environment Variables** section, add:
   * `API_PROXY_URL` = `https://nimbus-api-l32h.onrender.com` (the frontend proxies `/api/*` here, so the session cookie is first-party)
   * `NEXT_PUBLIC_WS_URL` = `wss://nimbus-api-l32h.onrender.com` (WebSockets go direct, authenticated by a stream ticket)
   * `NEXT_PUBLIC_API_URL` is no longer used and can be removed.
   * On the backend (Render), set `FRONTEND_URL` = `https://nimbusagent.vercel.app` and `OAUTH_REDIRECT_BASE_URL` = `https://nimbusagent.vercel.app`.
   * In the GitHub OAuth app, set the **Authorization callback URL** to `https://nimbusagent.vercel.app/api/auth/github/callback`.
5. Click **Deploy**.

Your live frontend at **`https://nimbusagent.vercel.app/`** communicates seamlessly with your cloud control plane!

---

## Database migrations

`entrypoint.sh` runs `alembic upgrade head` on every start but ignores a failure, and `main.lifespan`
also creates missing tables and adds missing columns. A database that was created by `lifespan`
rather than Alembic has no `alembic_version` row, so its upgrade is expected to fail (the first
migration tries to create existing tables) and only the `lifespan` path applies. Run `uv run alembic stamp head` once against such a database so later migrations
apply normally.
