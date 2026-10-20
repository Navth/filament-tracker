# syntax=docker/dockerfile:1
# Agent HTTP API (ft-agent serve) for Google Cloud Run.
#   docker build -t filament-agent agent/
#   docker run -p 8080:8080 --env-file agent/.env filament-agent

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FT_AGENT_HOME=/tmp/filament-agent \
    PORT=8080

COPY pyproject.toml README.md ./
COPY src ./src
# The demo fixture, so `--demo` works in the container too.
COPY tests/fixtures ./tests/fixtures
# Editable install keeps the source tree (and the fixture path) as-is.
RUN pip install -e ".[postgres]"

RUN useradd --system --uid 10001 app
USER app
EXPOSE 8080
# Configuration (model API key, SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY,
# FT_AGENT_DATABASE_URL, ...) comes from the environment at runtime.
CMD ["sh", "-c", "exec ft-agent serve --host 0.0.0.0 --port ${PORT}"]
