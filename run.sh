#!/usr/bin/env bash
# Open the diary. Requires the agent already deployed (device/build.sh).
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f .env ]; then
    echo "no .env: copy .env.example to .env and fill it in" >&2
    exit 1
fi
set -a; source .env; set +a
exec ./.venv/bin/python host/riddle.py "$@"
