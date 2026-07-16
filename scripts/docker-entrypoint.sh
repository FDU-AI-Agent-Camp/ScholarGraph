#!/bin/sh
# ScholarGraph container entrypoint: prepare persistent dirs, migrate DB, start API.
set -eu

DATA_ROOT="${SCHOLARGRAPH_DATA_ROOT:-/app/data}"

mkdir -p \
  "${DATA_ROOT}/graphs" \
  "${DATA_ROOT}/uploads" \
  "${DATA_ROOT}/chroma" \
  "${DATA_ROOT}/models/huggingface" \
  "${DATA_ROOT}/models/modelscope"

echo "[entrypoint] applying Alembic migrations..."
python /app/scripts/init_db.py

PORT="${PORT:-8080}"
echo "[entrypoint] starting uvicorn on 0.0.0.0:${PORT}"
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT}"
