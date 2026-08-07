# Cloud-Native AI Agent — Implementation Plan

## Product Intent

Build a Devin-style cloud software-engineering agent inspired by Harkirat
Singh's *Build This Project to Get Hired in 2026*. A user delegates a coding
task from a web application; a control-plane agent performs the work in an
ephemeral remote workspace, reports progress in real time, and delivers a
reviewable branch or pull request.

This is not a local CLI agent, a terminal wrapper, or an agent process that runs
inside the user's repository. The differentiators are isolation, multi-tenant
GitHub access, durable orchestration, browser-based validation, and a complete
session experience.

## Architecture Decisions

- Keep the **agent orchestrator outside** the workspace. It controls tool use,
  policy, lifecycle, and credentials.
- Create **one disposable workspace per task**. Docker is acceptable locally;
  production needs a stronger isolation provider behind the same interface.
- Use a **GitHub App**, not personal access tokens. Generate repository-scoped,
  short-lived installation tokens only when a workspace needs Git access.
- Persist tasks and append-only execution events. WebSockets distribute events;
  they are not the source of truth.
- Store logs, diffs, and screenshots as private artifacts and reference them by
  ID from task events.
- Require policy/approval for high-impact operations such as pushes, PRs,
  deployments, secret access, and unrestricted external requests.

## Delivery Sequence

1. Build durable task state, the event stream, and a local Docker workspace.
2. Add a single-agent shell/file loop that creates a tested patch.
3. Add the GitHub App, credential broker, and draft-PR handoff.
4. Add session replay, approvals, audit history, operational limits, and cleanup.
5. Add browser automation, then optional deployment, LSP, and MCP integrations.

## Definition of a V1

V1 accepts a task for an authorized repository, creates a fresh workspace,
clones the repository, edits and tests it, streams durable progress events, and
offers a human-reviewed draft PR. It safely handles cancellation and cleans up
the workspace. Embedded VS Code, multi-agent swarms, autonomous deployment, and
full IDE intelligence are deliberately deferred.

## Detailed Documents

- [Architecture](docs/architecture.md)
- [Delivery Roadmap](docs/roadmap.md)
- [Security Model](docs/security.md)
- [Source Research](research/README.md)
