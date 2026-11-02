#!/bin/sh
# Revive the ZIM console. Idempotent: exit if the API is already answering.
set -eu
if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8080/health; then
  exit 0
fi
cd /workspace/zim-media-api
if [ ! -x .venv/bin/uvicorn ]; then
  /usr/local/bin/python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
mkdir -p data
export APP_ENV=development
export API_KEY_REQUIRED=true
export PROXY_ENABLED=false
export DATABASE_URL=sqlite:////workspace/zim-media-api/data/zim.db
export DATA_DIR=/workspace/zim-media-api/data
export REDIS_URL=
export REDIS_REQUIRED=false
export EXTRACTION_BACKEND=local
export AUTO_CREATE_SCHEMA=true
cd /workspace/zim-media-api
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080 > /tmp/zim-api.log 2>&1 &
i=0
while [ "$i" -lt 40 ]; do
  if curl -sf -o /dev/null --max-time 1 http://127.0.0.1:8080/health; then
    exit 0
  fi
  i=$((i + 1))
  sleep 0.5
done
exit 1
