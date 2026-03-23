#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT/output"
mkdir -p "$LOG_DIR"

CRON_CMD="0 7,13,21 * * * cd $ROOT && /bin/bash $ROOT/run.sh >> $LOG_DIR/cron.log 2>&1"

CURRENT="$(crontab -l 2>/dev/null || true)"
{
  printf "%s\n" "$CURRENT" | grep -v "book_resale_monitor/run.sh" || true
  echo "$CRON_CMD"
} | crontab -

echo "Installed cron:" 
echo "$CRON_CMD"
