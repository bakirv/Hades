# =============================================================================
# HADES backend image — multi-stage, Linux only.
# =============================================================================
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps kept minimal; add build tooling only in the builder layer.
# postgresql-client provides pg_dump / pg_restore for the backup manager.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# ---- builder: install the package + deps into a venv ------------------------
FROM base AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
# Install with dev extras so lint/test/migrate work inside the container.
RUN pip install --upgrade pip && pip install ".[dev]"

# ---- runtime ----------------------------------------------------------------
FROM base AS runtime
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

# Run as non-root. Pre-create the volume-backed data directories owned by the
# runtime user so Docker initialises the named volumes with the right ownership
# (the process writes logs, liveness files, models, backups, etc. as uid 1000).
RUN useradd --create-home --uid 1000 hades \
    && mkdir -p /var/log/hades /var/run/hades \
       /app/config /app/models /app/backups /app/datasets /app/research /app/docs \
    && chown -R hades:hades /app /var/log/hades /var/run/hades
USER hades

EXPOSE 8000

# Default command is overridden by docker-compose (hades-api / hades-worker / …).
CMD ["hades-api"]
