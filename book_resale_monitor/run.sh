#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$ROOT/venv" ]; then
  python3 -m venv "$ROOT/venv"
fi

"$ROOT/venv/bin/pip" install -q -r "$ROOT/requirements.txt"
"$ROOT/venv/bin/python" "$ROOT/monitor.py"
