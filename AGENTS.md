# Repository Guidelines

## Project Structure & Module Organization

This repository is in architecture and validation stage. Its files are organized
as follows:

- `docs/` contains the product architecture, roadmap, and security model.
- `research/` contains the video transcript, derived artifacts, and collection
  utilities.
- `architecture_plan.md` is the concise implementation-plan entry point.

Put durable design decisions in `docs/`, and place research-only scripts and
inputs in `research/`. As application services are added, use top-level
directories named for their bounded responsibility (for example `frontend/`,
`control-plane/`, or `workspace-provider/`).

## Build, Test, and Development Commands

There is no build system or automated test suite yet. Use Python 3 directly:

```bash
python3 research/get_transcript.py    # fetch and save the configured transcript
python3 research/parse_transcript.py  # regenerate research/transcript_text.txt
```

`get_transcript.py` requires the `youtube-transcript-api` package. Install it in
an isolated virtual environment when setting up local development.

## Coding Style & Naming Conventions

Follow standard Python conventions: four-space indentation, `snake_case` for
functions and variables, and concise module names such as `parse_transcript.py`.
Use UTF-8 text files, context managers for file I/O, and explicit error messages
for network or parsing failures. Keep scripts focused on one task; extract shared
logic only when multiple scripts need it. No formatter or linter is configured,
so format code consistently with PEP 8.

## Testing Guidelines

Add tests alongside future code in a `tests/` directory, named
`test_<module>.py`. Prefer `pytest` for new automated tests. Cover successful
parsing and malformed or missing transcript inputs; avoid live network calls in
unit tests by using fixtures or mocks. Run the relevant script manually after
changing generated-output behavior.

## Commit & Pull Request Guidelines

Git history is not available in this workspace, so use short imperative commit
subjects, for example `Add transcript parsing validation`. Keep commits scoped to
one change. Pull requests should explain the purpose, list validation performed,
link related issues when applicable, and include before/after output or
screenshots when changing generated artifacts or documentation.

## Security & Configuration

Do not commit API keys, tokens, or downloaded credentials. If a future script
needs configuration, read it from environment variables and document required
variable names in the relevant README or design document.
