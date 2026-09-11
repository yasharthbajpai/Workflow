#!/usr/bin/env bash
# Render start command: optionally wipe the demo schema, then migrate + seed + serve.
set -euo pipefail

if [ "${RESET_DEMO_DATA:-0}" = "1" ]; then
  python -m app.reset_and_seed
else
  alembic upgrade head
  python -m app.seed
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
