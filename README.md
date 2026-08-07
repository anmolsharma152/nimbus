# Cloud Agent

Cloud Agent is a from-scratch exploration of a cloud-native autonomous software
engineering agent, inspired by Harkirat Singh's *Build This Project to Get Hired
in 2026* video. It is intentionally not a local coding CLI: users delegate work
through a web product, while an isolated cloud workspace clones repositories,
edits code, runs tests, uses a browser, and returns a reviewable pull request.

The repository is in the architecture and validation stage; no product services
have been implemented yet.

## Product Boundary

The control plane owns users, sessions, policy, credentials, agent execution,
events, and audit records. Each task gets a disposable workspace with only the
repository and short-lived capabilities it needs. The agent itself must remain
outside that workspace.

See [Architecture](docs/architecture.md), [Delivery Roadmap](docs/roadmap.md),
and [Security Model](docs/security.md).

## Repository Layout

```text
docs/       Product, architecture, security, and delivery decisions
research/   Video transcript, derived artifacts, and collection utilities
```

## Research Utilities

```bash
python3 research/parse_transcript.py  # rebuild research/transcript_text.txt
python3 research/get_transcript.py    # fetch the configured YouTube transcript
```

The latter requires `youtube-transcript-api`. Research files are inputs to
design work; do not treat them as application source code.
