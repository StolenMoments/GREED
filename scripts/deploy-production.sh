#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/home/opc/GREED}"
BRANCH="${DEPLOY_BRANCH:-master}"
SHA="${DEPLOY_SHA:?DEPLOY_SHA is required}"
LOCK_FILE="${DEPLOY_LOCK_FILE:-/tmp/greed-deploy.lock}"

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*"
}

cd "$APP_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "Another deployment is already running."
  exit 1
fi

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  log "Tracked local changes exist in $APP_DIR. Refusing to deploy over them."
  git status --short
  exit 1
fi

log "Fetching origin/$BRANCH."
git fetch origin "$BRANCH"
git checkout "$BRANCH"

log "Fast-forwarding to $SHA."
git merge --ff-only "$SHA"

log "Installing pinned Python dependencies."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.lock.txt

log "Installing pinned frontend dependencies."
npm ci --prefix frontend

log "Restarting services."
sudo systemctl restart greed-backend.service greed-frontend.service

log "Checking backend health."
curl -fsS http://127.0.0.1:8000/api/health >/dev/null

log "Checking frontend health."
curl -fsSI http://127.0.0.1:5173 >/dev/null

log "Deployment complete: $(git rev-parse --short HEAD)."
