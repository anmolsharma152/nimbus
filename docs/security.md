# Security Model

This describes what the code enforces today. Planned controls that are **not built yet** are
listed at the end; don't rely on them.

## Trust zones

- **Trusted:** the FastAPI control plane, the arq worker, PostgreSQL and Redis. Only these hold
  provider keys, decrypted user credentials and `JWT_SECRET_KEY`.
- **Untrusted:** the browser, everything inside a task workspace (cloned repository contents,
  commands the LLM emits, their output), and any text that came from a repository.

## Identity and access

- GitHub OAuth (`read:user,user:email,repo` scope). The session is a JWT in the HTTP-only
  `nimbus_session` cookie, kept first-party through the frontend's `/api` proxy. WebSockets use a
  60-second, task-scoped stream ticket (`POST /api/tasks/{id}/stream-ticket`), never the session JWT.
- Every task endpoint is owner-scoped. Someone else's task returns **404**, not 403.
- **Repo tasks require sign-in** (401 otherwise). Signed-out visitors can only run tasks without a
  repository: at most 2 at a time, and `ANON_TASKS_PER_HOUR` (default 10) per hour shared by all of them.
- Signed-in quotas: free 3 concurrent / 20 runs per hour, pro 10 / 100. New tasks and follow-up
  messages count toward the hourly limit; retries don't (`app/ratelimit.py`).

## Credentials

- User GitHub tokens (OAuth or a saved PAT) and BYOK LLM keys are encrypted at rest with Fernet.
  The key is derived from `JWT_SECRET_KEY`, so changing that secret makes stored credentials
  unreadable unless they are re-encrypted.
- **There is no server-wide GitHub token.** A task clones, pushes and opens PRs only with its
  owner's own credentials.
- Settings fields holding secrets are `SecretStr`, so they never appear in reprs, logs or test output.
  Logs record prompt lengths and ids, never prompts, tokens or keys.

## Workspace isolation

One disposable workspace per task, removed when the task ends, fails, is cancelled or hits
`TASK_TIMEOUT_SECONDS` (30 min). In Docker mode a periodic reaper also removes containers and
volumes left behind by a worker crash. Commands time out after 300 s. There are two implementations (`app/workspace.py`):

| | DockerWorkspace (local, any host with Docker) | SubprocessWorkspace (Render/Railway production) |
| :--- | :--- | :--- |
| Process isolation | Container as uid 10001, `cap_drop=ALL`, `no-new-privileges` | Per-task UID (200000+) when the worker runs as root; otherwise the worker's own UID |
| Resource limits | 1 GB RAM, 2 CPUs, 256 PIDs | **None** beyond the 300 s command timeout and the task time limit |
| Environment | Clean container env | Scrubbed env (PATH, HOME, LANG, TERM only) |
| Network | Unrestricted outbound | Unrestricted outbound |

Production currently runs SubprocessWorkspace, so the cgroup limits above apply only where Docker
is available.

## Git operations

- Anything that holds the GitHub token (clone, push) runs outside the agent's user, in a separate
  helper container or private directory, and never reads the agent's `.git`. The token is passed as
  an auth header scoped to `https://github.com/` through `GIT_CONFIG_*` env vars, never written
  to disk or to `.git/config`, and hooks are disabled.
- A push replays the agent's patch onto a fresh clone of the base commit, so agent-controlled git
  config, hooks or history cannot affect it.
- **Branch rules:** user-supplied branch names must be valid refs and not a default or long-lived
  name (`main`, `master`, `develop`, `release/*`, `hotfix/*`, ...). Every push uses
  `--force-with-lease`: a first push only creates a branch that doesn't exist yet, so no
  existing branch is ever touched, the repo's real default branch included. A follow-up or retry
  only replaces the commit Nimbus itself pushed last, and is refused if anyone else has pushed since.
- Before running, the worker checks the owner's access to the repo (`GET /repos/{o}/{r}`). Without
  write access, changes go to a fork in the owner's account and the draft PR is opened from there.
  PRs always target the repo's default branch.

## Data handling

- Task events (commands, output, screenshots) are stored in PostgreSQL and shown only to the task owner.
- Repository content and LLM output are untrusted input and can attempt prompt injection. The
  agent's commands run only inside the workspace, which holds no credentials.

## Not built yet

These appeared in earlier plans and are **not implemented**:

- GitHub App with short-lived, repository-scoped installation tokens (tasks use the user's OAuth token or PAT).
- Outbound network restrictions for workspaces.
- Resource limits in SubprocessWorkspace (production), or a microVM workspace provider.
- Approval steps for high-impact actions (pushes, PRs, destructive commands); pushes and draft PRs are automatic.
- An immutable audit trail of tool decisions, and redaction of credentials from command output.
- Artifact retention limits.
