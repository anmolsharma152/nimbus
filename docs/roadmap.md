# Delivery Roadmap

## Phase 0 — Foundation

Choose the initial stack, define the repository interface, and create local
development infrastructure. Establish Postgres for durable state, a queue for
background work, object storage for artifacts, and structured logs. Define a
task lifecycle before adding an LLM.

**Exit criterion:** a fake worker can create, update, replay, cancel, and finish
a task through the API and WebSocket UI.

## Phase 1 — Safe single-agent execution

Implement a single worker and local Docker workspace adapter. Give the agent
shell, file read/write, and diff tools. Clone a public fixture repository into a
fresh workspace, run tests, capture output, and always clean up.

**Exit criterion:** a task changes a fixture repository and produces a tested
patch with a complete event timeline.

## Phase 2 — GitHub workflow

Create the GitHub App, installation callback, encrypted installation records,
and short-lived repository-scoped token broker. Add branch creation, commits,
and draft PR creation behind an explicit approval policy.

**Exit criterion:** an authorized private repository receives a draft PR without
persisting a long-lived repository credential in the workspace.

## Phase 3 — Product-grade visibility

Add session history, reconnect/replay, file diffs, command output, approvals,
and artifact links. Add budgets, cancellation, timeouts, cleanup jobs, audit
records, and operational dashboards.

**Exit criterion:** an interrupted browser session can reconnect and accurately
replay task state.

## Phase 4 — Browser and advanced integrations

Add Playwright browser tools, screenshots, and app-preview support. Then add
optional issue tracker, deployment, LSP, and MCP integrations one at a time.

**Exit criterion:** the agent can validate a web change with a stored screenshot
and a human can review every privileged action.
