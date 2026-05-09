#!/usr/bin/env bash
# Deploy/update backend-mobile on OCI Oracle Linux.
# Usage: bash deploy/deploy-mobile.sh
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$DEPLOY_DIR")"
APP_DIR="$PROJECT_DIR/backend-mobile"
SERVICE=greed-mobile
BRANCH=master

echo "==> backend-mobile deploy start"
echo "    PROJECT_DIR: $PROJECT_DIR"

# 1. Update source from GitHub. Fail if the server checkout cannot fast-forward.
echo "--> update source: origin/$BRANCH"
git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree > /dev/null
git -C "$PROJECT_DIR" fetch origin "$BRANCH"
git -C "$PROJECT_DIR" checkout "$BRANCH"
git -C "$PROJECT_DIR" pull --ff-only origin "$BRANCH"

# 2. Create Python venv if needed.
if [ ! -d "$APP_DIR/venv" ]; then
    echo "--> create venv"
    python3 -m venv "$APP_DIR/venv"
fi

# 3. Install dependencies.
echo "--> install dependencies"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# 4. Register systemd service on first run.
SERVICE_FILE=/etc/systemd/system/$SERVICE.service
if [ ! -f "$SERVICE_FILE" ]; then
    echo "--> register systemd service"
    sed "s|/opt/greed|$PROJECT_DIR|g; s|User=opc|User=$(whoami)|g; s|Group=opc|Group=$(whoami)|g" \
        "$DEPLOY_DIR/greed-mobile.service" | sudo tee "$SERVICE_FILE" > /dev/null
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE"
fi

# 5. Register nginx config on first run.
NGINX_CONF=/etc/nginx/conf.d/$SERVICE.conf
if [ ! -f "$NGINX_CONF" ]; then
    echo "--> register nginx config"
    sudo cp "$DEPLOY_DIR/nginx-mobile.conf" "$NGINX_CONF"
fi

# 6. Restart service.
echo "--> restart service"
sudo systemctl restart "$SERVICE"

# 7. Validate and reload nginx.
echo "--> nginx reload"
sudo nginx -t
sudo systemctl reload nginx

# 8. Show status.
echo "--> service status"
sudo systemctl status "$SERVICE" --no-pager

echo ""
echo "==> deploy complete"
echo "    health check: curl http://localhost:8001/health"
