#!/usr/bin/env bash
set -euo pipefail

STORAGE_DIR="${STORAGE_PATH:-/app/storage}"

mkdir -p "${STORAGE_DIR}"
chown -R appuser:appuser "${STORAGE_DIR}"

echo "[entrypoint] running database migrations (alembic upgrade head)..."
gosu appuser alembic upgrade head

echo "[entrypoint] starting: $*"
exec gosu appuser "$@"