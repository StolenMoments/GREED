#!/usr/bin/env bash
# OCI Oracle Linux 서버에서 backend-mobile 배포/업데이트 스크립트
# 사용법: bash deploy/deploy-mobile.sh
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$DEPLOY_DIR")"
APP_DIR="$PROJECT_DIR/backend-mobile"
SERVICE=greed-mobile

echo "==> backend-mobile 배포 시작"
echo "    PROJECT_DIR: $PROJECT_DIR"

# 1. Python venv 생성 (없을 경우)
if [ ! -d "$APP_DIR/venv" ]; then
    echo "--> venv 생성"
    python3 -m venv "$APP_DIR/venv"
fi

# 2. 의존성 설치
echo "--> 의존성 설치"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# 3. systemd 서비스 등록 (처음 실행 시)
SERVICE_FILE=/etc/systemd/system/$SERVICE.service
if [ ! -f "$SERVICE_FILE" ]; then
    echo "--> systemd 서비스 등록"
    sed "s|/opt/greed|$PROJECT_DIR|g; s|User=opc|User=$(whoami)|g; s|Group=opc|Group=$(whoami)|g" \
        "$DEPLOY_DIR/greed-mobile.service" | sudo tee "$SERVICE_FILE" > /dev/null
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE"
fi

# 4. nginx 설정 등록 (처음 실행 시) — Oracle Linux: conf.d 방식
NGINX_CONF=/etc/nginx/conf.d/$SERVICE.conf
if [ ! -f "$NGINX_CONF" ]; then
    echo "--> nginx 설정 등록"
    sudo cp "$DEPLOY_DIR/nginx-mobile.conf" "$NGINX_CONF"
fi

# 5. 서비스 재시작
echo "--> 서비스 재시작"
sudo systemctl restart "$SERVICE"

# 6. nginx 설정 검사 및 reload
echo "--> nginx reload"
sudo nginx -t
sudo systemctl reload nginx

# 7. 상태 확인
echo "--> 서비스 상태"
sudo systemctl status "$SERVICE" --no-pager

echo ""
echo "==> 배포 완료"
echo "    health check: curl http://localhost:8001/health"
