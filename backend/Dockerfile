FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8000 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install system dependencies & docker client (for workspace spawning)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency configuration
COPY pyproject.toml uv.lock ./

# Install Python dependencies into virtual environment
RUN uv sync --frozen --no-dev

# Copy application source code and migrations
COPY . /app/

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh 2>/dev/null || true

EXPOSE ${PORT}

CMD ["/bin/bash", "/app/entrypoint.sh"]
