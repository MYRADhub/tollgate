#!/usr/bin/env bash
# Boot an isolated API and worker for the browser tests: fresh SQLite, local files,
# no inference key (deterministic fallbacks) and no mail.
set -euo pipefail
DIR="$(mktemp -d -t tollgate-e2e)"
cd "$(dirname "$0")/../../backend"
export TOLLGATE_DATABASE_URL="sqlite:///$DIR/e2e.db" TOLLGATE_LOCAL_STORAGE_DIR="$DIR/storage" \
  TOLLGATE_INFERENCE_API_KEY="${E2E_INFERENCE_API_KEY:-}" TOLLGATE_MAIL_ENABLED=false TOLLGATE_INTAKE_PER_IP_PER_HOUR=1000 TOLLGATE_RESETS_PER_IP_PER_HOUR=1000 TOLLGATE_COLLEAGUE_REPLY_S=3 TOLLGATE_RESET_COOLDOWN_S=0
uv run python -c "from tollgate.db import init_db; init_db()"
uv run python -m tollgate.worker &
WORKER=$!
uv run uvicorn tollgate.api:app --port "${E2E_API_PORT:-8100}" &
API=$!
trap 'kill $WORKER $API 2>/dev/null; wait' EXIT INT TERM
wait $API
