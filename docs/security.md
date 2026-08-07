# Security Model

## Trust Zones

The browser and repository workspace are untrusted. The control plane is trusted
and is the only component allowed to store installation identifiers, encrypted
integration metadata, and provider credentials. Never put a GitHub App private
key, user token, or shared deployment secret in a workspace.

## Workspace Controls

Create one disposable workspace per task. Mount only its assigned repository and
give it a repository-scoped, short-lived installation token when required.
Constrain CPU, memory, disk, task duration, processes, and outbound network
access. Destroy the workspace after completion or timeout, and record cleanup
failure for retry.

## Tool Policy

Classify tools by impact. Reads are normally allowed; workspace writes and test
commands are policy-controlled; pushes, PR creation, external requests,
deployments, dependency installation, and destructive commands require explicit
approval or narrowly configured rules. Record tool request, decision, actor,
and result in an immutable audit trail.

## Data Handling

Redact tokens and common credential formats from logs, terminal output, browser
artifacts, and prompts. Store artifacts privately with task-scoped access and
retention limits. Do not place secrets in event payloads. Treat repository text,
issues, and web content as untrusted input because they can attempt prompt
injection.
