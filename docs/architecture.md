# Architecture

## Goal

Build a multi-tenant cloud coding agent that accepts a repository task, works
autonomously in an isolated workspace, continuously reports progress, and
delivers a branch or pull request. It is a distributed product, not a hosted
terminal session.

## System Boundary

```text
Browser UI ↔ API / WebSocket gateway ↔ control plane ↔ agent orchestrator
                                      ↕                 ↕
                           Postgres, queue, object store  workspace provider
                                                          ↕
                                     GitHub, shell, files, tests, browser tools
```

The control plane is trusted. It owns identity, tenant membership, task state,
policy, audit events, and credential brokering. A workspace is untrusted: it
runs repository code and receives only task-scoped, short-lived credentials.

## Core Components

### Web application

The UI creates tasks and renders an event timeline, terminal streams, diffs,
browser artifacts, approvals, and final handoff. It reconnects by replaying
persisted events rather than relying on an in-memory WebSocket.

### Control plane and orchestration

An API service persists sessions and enqueues work. A worker runs the LLM tool
loop, validates tool requests against policy, and emits append-only events. Tool
execution must be idempotent or carry a command identifier so retries never
duplicate a commit, deployment, or PR.

### Workspace provider

Use a provider interface: `create`, `exec`, `read`, `write`, `snapshot`,
`destroy`, and `stream_logs`. Docker is suitable for local development. A
production implementation should use stronger per-workspace isolation (for
example microVMs) and enforce CPU, memory, disk, execution-time, and network
egress limits.

### Integrations

GitHub access uses a GitHub App. The control plane generates a repository-
scoped installation token at workspace creation and revokes access by destroying
the workspace. Browser automation is a separate capability, backed by Playwright
and artifact storage. Deployment, issue trackers, and MCP integrations are
post-V1 capabilities with explicit scopes and approvals.

## Event Contract

Every meaningful state change becomes a durable event: `task.created`,
`workspace.ready`, `tool.requested`, `tool.started`, `tool.completed`,
`approval.required`, `artifact.created`, `task.completed`, and `task.failed`.
The UI subscribes to this stream; logs and screenshots live in object storage
and events contain references rather than large payloads.

## V1 Non-Goals

Do not begin with a VS Code server, LSP integration, multi-agent swarms,
automatic deployment, or unrestricted internet access. First prove a reliable
single-agent path from task to tested branch/PR.
