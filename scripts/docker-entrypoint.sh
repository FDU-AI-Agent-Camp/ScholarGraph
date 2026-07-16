#!/bin/sh
# ScholarGraph container entrypoint: prepare persistent dirs, migrate DB, start API.
set -eu

DATA_ROOT="${SCHOLARGRAPH_DATA_ROOT:-/app/data}"
MODELS_ROOT="${SCHOLARGRAPH_MODELS_ROOT:-/app/models}"

mkdir -p \
  "${DATA_ROOT}/graphs" \
  "${DATA_ROOT}/uploads" \
  "${DATA_ROOT}/chroma" \
  "${MODELS_ROOT}/huggingface" \
  "${MODELS_ROOT}/huggingface/hub" \
  "${MODELS_ROOT}/modelscope"

# Prefer volume-backed caches even if Zeabur forgot to set HF_HOME / MODELSCOPE_CACHE.
export HF_HOME="${HF_HOME:-${MODELS_ROOT}/huggingface}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-${HF_HOME}/hub}"
export MODELSCOPE_CACHE="${MODELSCOPE_CACHE:-${MODELS_ROOT}/modelscope}"

echo "[entrypoint] data_root=${DATA_ROOT} models_root=${MODELS_ROOT}"
echo "[entrypoint] HF_HOME=${HF_HOME} MODELSCOPE_CACHE=${MODELSCOPE_CACHE}"
echo "[entrypoint] applying Alembic migrations..."
python /app/scripts/init_db.py

PORT="${PORT:-8080}"
echo "[entrypoint] starting uvicorn on 0.0.0.0:${PORT}"
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT}"
