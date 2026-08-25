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
                     [ Ephemeral Sandboxes (Docker / microVMs) ]
```

---

## Deployment Pathway 1: 1-Click Render Blueprint (Recommended)

Render allows you to provision the entire backend stack (FastAPI Web Service + arq Background Worker + PostgreSQL + Redis) from the included [`render.yaml`](../render.yaml).

### Steps:
1. Log in to your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** → **Blueprint**.
3. Connect your GitHub repository: `anmolsharma152/nimbus`.
4. Render will detect [`render.yaml`](../render.yaml) and automatically configure:
   * **`nimbus-api`** (FastAPI Web Service)
   * **`nimbus-worker`** (Background Worker)
   * **`nimbus-db`** (PostgreSQL 16)
   * **`nimbus-redis`** (Redis instance)
5. Fill in the prompted secret environment variables:
   * `GEMINI_API_KEY`: Your Google Gemini API Key.
   * `GITHUB_TOKEN`: (Optional) GitHub Personal Access Token for PR creation.
6. Click **Apply**.
7. Copy your public `nimbus-api` URL (e.g., `https://nimbus-api.onrender.com`).

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
2. Add environment variables: `DATABASE_URL`, `REDIS_URL`, `GEMINI_API_KEY`.
3. Start command: `/bin/bash /app/entrypoint.sh`.

---

## Deploying the Frontend to Vercel

Once your backend is live and you have your public API URL (e.g. `https://nimbus-api.onrender.com`):

### Steps:
1. Open the [Vercel Import Link](https://vercel.com/new/import?framework=nextjs&path=frontend&project-name=frontend&provider=github&s=https%3A%2F%2Fgithub.com%2Fanmolsharma152%2Fnimbus) from your email or go to [vercel.com/new](https://vercel.com/new).
2. Select your repository: **`anmolsharma152/nimbus`**.
3. Set the **Root Directory** to: `frontend`.
4. In the **Environment Variables** section, add:
   * `NEXT_PUBLIC_API_URL` = `https://nimbus-api.onrender.com` (your backend URL)
   * `NEXT_PUBLIC_WS_URL` = `wss://nimbus-api.onrender.com` (WebSocket protocol `wss://`)
5. Click **Deploy**.

Your live frontend will now communicate seamlessly with your cloud control plane!
