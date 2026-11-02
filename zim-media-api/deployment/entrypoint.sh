#!/bin/sh
set -eu
if [ "${AUTO_CREATE_SCHEMA:-false}" = "false" ]; then
  alembic upgrade head
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*"
