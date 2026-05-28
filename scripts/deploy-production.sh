#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/home/opc/GREED}"
BRANCH="${DEPLOY_BRANCH:-master}"
SHA="${DEPLOY_SHA:?DEPLOY_SHA is required}"
LOCK_FILE="${DEPLOY_LOCK_FILE:-/tmp/greed-deploy.lock}"

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*"
}

wait_for_url() {
  local label="$1"
  local url="$2"
  local curl_args=("${@:3}")

  for attempt in $(seq 1 30); do
    if curl -fsS "${curl_args[@]}" "$url" >/dev/null; then
      log "$label is healthy."
      return 0
    fi

    log "$label is not ready yet; retrying ($attempt/30)."
    sleep 1
  done

  log "$label did not become healthy."
  return 1
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
wait_for_url "Backend" "http://127.0.0.1:8000/api/health"

log "Checking frontend health."
wait_for_url "Frontend" "http://127.0.0.1:5173" -I

log "Deployment complete: $(git rev-parse --short HEAD)."
