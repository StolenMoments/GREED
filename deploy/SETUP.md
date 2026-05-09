# GREED Mobile API — OCI 배포 가이드

`backend-mobile` (읽기 전용 FastAPI 서버)을 OCI Ubuntu 인스턴스에 배포하는 절차.

- 도메인: `mygreed.shop`
- 서버: OCI (Ubuntu 22.04 LTS)
- HTTPS: Let's Encrypt (certbot)

---

## 사전 요구사항

| 항목 | 버전 |
|------|------|
| OS | Ubuntu 22.04 LTS |
| Python | 3.12 이상 |
| nginx | 1.18 이상 |
| MariaDB | 10.6 이상 (OCI 인스턴스에 이미 운영 중) |

### OCI 포트 개방

OCI 콘솔 → **Networking → Virtual Cloud Networks → Security Lists** 에서 인바운드 규칙 추가:

| 포트 | 프로토콜 | 용도 |
|------|----------|------|
| 80 | TCP | HTTP (certbot 인증 + HTTPS 리다이렉트) |
| 443 | TCP | HTTPS |

ufw도 함께 허용:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload
```

### DNS 설정

도메인 등록 업체(가비아 등)에서 A 레코드를 추가한다.

```
mygreed.shop  →  OCI_SERVER_IP
```

설정 후 전파 확인:

```bash
nslookup mygreed.shop
# → Address: OCI_SERVER_IP 가 나와야 함
```

> DNS 전파는 최대 30분 걸린다. certbot은 도메인이 서버 IP로 연결되어야 발급된다.

---

## 1. 소스 배포

### 방법 A — git clone (신규 서버)

```bash
sudo mkdir -p /opt/greed
sudo chown ubuntu:ubuntu /opt/greed
cd /opt/greed
git clone https://github.com/YOUR_REPO greed
```

### 방법 B — rsync (로컬 → 서버 업데이트)

```bash
rsync -av --exclude='__pycache__' --exclude='venv' \
  backend-mobile/ ubuntu@OCI_SERVER_IP:/opt/greed/backend-mobile/
rsync -av deploy/ ubuntu@OCI_SERVER_IP:/opt/greed/deploy/
```

---

## 2. `.env` 파일 설정

```bash
cp /opt/greed/backend-mobile/.env.example /opt/greed/backend-mobile/.env
nano /opt/greed/backend-mobile/.env
```

```env
DATABASE_URL=mysql+pymysql://greed_mobile:DB_PASSWORD@146.56.146.157:3306/greed?charset=utf8mb4
MOBILE_API_KEY=여기에_강력한_키_입력
```

`MOBILE_API_KEY` 생성:

```bash
openssl rand -hex 32
# 출력 예: a3f8c2e1b4d7... (64자리 16진수)
```

> **주의:** `.env` 파일은 git에 올리지 않는다.

---

## 3. MariaDB 읽기 전용 계정 생성

MariaDB 서버(146.56.146.157)에 접속해 실행한다.

```bash
mysql -u root -p
```

```sql
CREATE USER 'greed_mobile'@'%' IDENTIFIED BY 'STRONG_PASSWORD';
GRANT SELECT ON greed.* TO 'greed_mobile'@'%';
FLUSH PRIVILEGES;

-- 확인
SHOW GRANTS FOR 'greed_mobile'@'%';
```

생성 후 `.env`의 `DATABASE_URL` 사용자를 `greed_mobile`로 설정한다.

---

## 4. Python venv 및 의존성 설치

```bash
cd /opt/greed/backend-mobile
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
```

---

## 5. systemd 서비스 등록

```bash
sudo cp /opt/greed/deploy/greed-mobile.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable greed-mobile
sudo systemctl start greed-mobile
```

상태 확인:

```bash
sudo systemctl status greed-mobile
# → Active: active (running) 이어야 함

curl http://localhost:8001/health
# → {"status":"ok"}
```

---

## 6. nginx 설치

```bash
sudo apt update
sudo apt install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

---

## 7. Let's Encrypt 인증서 발급

### 7-1. certbot 설치

```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 7-2. 인증서 발급

> DNS가 서버 IP로 연결된 상태에서 실행해야 한다.

```bash
sudo certbot --nginx -d mygreed.shop
```

실행 중 아래 항목을 입력한다:

1. 이메일 주소 입력 (갱신 만료 알림 수신용)
2. 이용약관 동의: `A`
3. 뉴스레터 수신 여부: `N` (선택)

발급 성공 시 출력:

```
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/mygreed.shop/fullchain.pem
Key is saved at:         /etc/letsencrypt/live/mygreed.shop/privkey.pem
```

### 7-3. nginx 설정 적용

certbot이 nginx 설정을 자동으로 수정한다. 그러나 우리 설정 파일을 직접 사용하는 경우 아래 절차로 적용한다.

```bash
sudo cp /opt/greed/deploy/nginx-mobile.conf /etc/nginx/sites-available/greed-mobile
sudo ln -s /etc/nginx/sites-available/greed-mobile /etc/nginx/sites-enabled/

# 기본 nginx 설정 비활성화 (포트 80 충돌 방지)
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t
# → syntax is ok / test is successful 이어야 함

sudo systemctl reload nginx
```

### 7-4. 자동 갱신 확인

Let's Encrypt 인증서는 90일마다 만료된다. certbot이 systemd 타이머를 자동 등록한다.

```bash
sudo systemctl status certbot.timer
# → Active: active (waiting) 이어야 함

# 갱신 테스트 (실제 갱신 없이 시뮬레이션)
sudo certbot renew --dry-run
# → Congratulations, all simulated renewals succeeded 이어야 함
```

---

## 8. 배포 스크립트 사용 (이후 업데이트)

소스 코드 변경 후 재배포:

```bash
cd /opt/greed
bash deploy/deploy-mobile.sh
```

---

## 9. 기동 확인 체크리스트

```bash
# 1. uvicorn health check (서버 내부)
curl http://localhost:8001/health
# → {"status":"ok"}

# 2. HTTP → HTTPS 리다이렉트
curl -I http://mygreed.shop/health
# → HTTP/1.1 301 Moved Permanently

# 3. HTTPS health check
curl https://mygreed.shop/health
# → {"status":"ok"}

# 4. 인증 헤더 없이 호출 → 422
curl https://mygreed.shop/analyses
# → {"detail":[{"msg":"Field required",...}]}

# 5. 잘못된 API Key → 401
curl -H "X-API-Key: wrong" https://mygreed.shop/analyses
# → {"detail":"Invalid API key"}

# 6. 올바른 API Key → 200
curl -H "X-API-Key: YOUR_KEY" https://mygreed.shop/analyses
# → {"items":[...],"page":1,"per_page":20,...}
```

---

## 10. 모바일 앱 설정

`mobile/.env` 파일 (또는 EAS 환경변수):

```env
EXPO_PUBLIC_API_URL=https://mygreed.shop
```

---

## 11. 트러블슈팅

### certbot 발급 실패: `Connection refused` / `Timeout`

- OCI Security List에서 80 포트 인바운드 허용 여부 확인
- ufw에서 80 포트 허용 여부 확인: `sudo ufw status`
- nginx가 실행 중인지 확인: `sudo systemctl status nginx`
- DNS가 서버 IP를 가리키는지 확인: `nslookup mygreed.shop`

### certbot 발급 실패: `Domain not pointing to server`

```bash
curl -4 ifconfig.me          # 서버 공인 IP 확인
nslookup mygreed.shop        # DNS A 레코드 확인
```

두 값이 일치해야 한다. DNS 전파 완료 후 재시도.

### 서비스가 시작하지 않는 경우

```bash
sudo journalctl -u greed-mobile -n 50 --no-pager
```

- `Can't connect to MySQL`: MariaDB 호스트/포트/계정 확인
- `MOBILE_API_KEY not configured`: `.env` 파일 경로 및 내용 확인
- `ModuleNotFoundError`: `venv/bin/pip install -r requirements.txt` 재실행

### nginx 502 Bad Gateway

```bash
sudo systemctl status greed-mobile    # 서비스 실행 중 확인
curl http://localhost:8001/health     # uvicorn 직접 연결 테스트
sudo nginx -t                          # nginx 설정 문법 확인
```

### 로그 실시간 확인

```bash
sudo journalctl -u greed-mobile -f
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```
