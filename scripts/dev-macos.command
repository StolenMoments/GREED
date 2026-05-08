#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

BACK_COMMAND='cd "$1" && if [ -x .venv/bin/python ]; then .venv/bin/python -m uvicorn backend.main:app --reload; elif command -v python3 >/dev/null 2>&1; then python3 -m uvicorn backend.main:app --reload; else python -m uvicorn backend.main:app --reload; fi'
FRONT_COMMAND='cd "$1" && npm run front'

osascript - "$ROOT_DIR" "$BACK_COMMAND" "$FRONT_COMMAND" <<'APPLESCRIPT'
on run argv
set rootDir to item 1 of argv
set backCommand to item 2 of argv
set frontCommand to item 3 of argv

tell application "Terminal"
  activate
  do script "/bin/bash -lc " & quoted form of backCommand & " -- " & quoted form of rootDir
  do script "/bin/bash -lc " & quoted form of frontCommand & " -- " & quoted form of rootDir
end tell
end run
APPLESCRIPT
