# Delivery Roadmap

`TASKS.md` is the detailed checklist; this page is the short version.

## Done

- **Phases 0–5:** durable task state and event stream, the 3-tier LLM agent loop, GitHub branches
  and draft PRs, GitHub OAuth with owner-scoped tasks, the encrypted BYOK vault and onboarding,
  Redis event fan-out with authenticated streams, screenshots, and the eval harness.
- **Hardening (2026-10):**
  - Auth bypass fixes, internal event authentication, task time limit and reliable workspace teardown.
  - `SecretStr` settings, sandbox isolation with the token kept out of the agent's reach, resilient WebSocket streams.
  - Structured logging, first-party session cookie via the `/api` proxy, CI quality gates.
  - Repo tasks require sign-in, there is no server GitHub token, and protected branches are rejected. Pushes can never touch a branch Nimbus didn't create.
  - Repo access is checked before running, with a fork flow when the user can't push. PRs target the default branch.
  - Follow-ups continue the same task, branch and PR.
  - Task page as a conversation: one turn per goal / follow-up / retry, collapsible command blocks with exit codes, a status banner, and a follow-up composer under the thread. Repo search on the home page works, and model choices are saved per account and used by the worker.

## Next

1. **Smaller fixes:** the Gemini tier is skipped unless the server has `GEMINI_API_KEY`, so a user's own Gemini key alone never works; pushing to an empty repo;
   clones are full depth (a shallow clone must still reach a follow-up's base commit); `arq` `max_jobs` on the 512 MB Render instance; `alembic stamp head` on
   databases created by `main.lifespan`.
2. **Workspace isolation in production:** resource and network limits for SubprocessWorkspace, or a
   `WorkspaceProvider` protocol with a microVM backend (Fly Machines / Modal / Firecracker).
3. **Later:** GitHub App installation tokens, approvals for high-impact actions, audit trail,
   steering a run while it is in progress, code indexing / LSP diagnostics.
