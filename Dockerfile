# syntax=docker/dockerfile:1.7

# ── Stage 1: Vue 3 frontend ──────────────────────────────────────────
FROM node:22-bookworm-slim AS frontend-builder

# Keep repo-relative layout so vue-tsc can resolve
# frontend/src/** → ../../../docs/api/fixtures/*.json
WORKDIR /src

COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN npm ci --prefix frontend

COPY frontend/ ./frontend/
COPY docs/api/fixtures ./docs/api/fixtures

WORKDIR /src/frontend
# Same-origin API via FastAPI reverse path (/api/v1)
ENV VITE_API_BASE_URL=
ENV VITE_USE_MOCK=false
RUN npm run build

# ── Stage 2: Python runtime (API + MinerU + SPA) ─────────────────────
FROM python:3.12-slim-bookworm AS runtime

# MinerU / OpenCV runtime libraries
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update -qq \
    && apt-get install -y --no-install-recommends \
        curl \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libxcb1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Dependency layer (cached until lock / pyproject changes)
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra mineru --no-install-project

# Application source
COPY backend ./backend
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
COPY docs/api ./docs/api
COPY .env.prod ./.env.prod

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra mineru

COPY --from=frontend-builder /src/frontend/dist ./frontend/dist

COPY scripts/docker-entrypoint.sh /app/scripts/docker-entrypoint.sh
RUN chmod +x /app/scripts/docker-entrypoint.sh \
    && mkdir -p \
        /app/data/graphs \
        /app/data/uploads \
        /app/data/chroma \
        /app/data/models/huggingface \
        /app/data/models/modelscope

# Defaults for Zeabur single Volume at /app/data (overridable via env)
ENV APP_PROFILE=prod \
    APP_ENV=production \
    DEBUG=false \
    DATABASE_URL=sqlite:////app/data/scholargraph.db \
    GRAPH_DATA_DIR=/app/data/graphs \
    UPLOAD_DIR=/app/data/uploads \
    CHROMADB_PATH=/app/data/chroma \
    HF_HOME=/app/data/models/huggingface \
    MODELSCOPE_CACHE=/app/data/models/modelscope \
    INGEST_MINERU_MODEL_SOURCE=modelscope \
    INGEST_MINERU_ENABLED=true \
    INGEST_ROUTE=auto \
    GROBID_FALLBACK_PYMUPDF=true \
    PORT=8080

EXPOSE 8080

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
