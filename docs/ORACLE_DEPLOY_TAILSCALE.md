# Oracle Cloud 배포 + Tailscale 기반 프라이빗 접속

## 목적

Oracle Cloud 컴퓨트 인스턴스에 greed 앱을 배포하고, 개인 소유 5대 기기(iPad, Galaxy S23, 노트북 2대, 데스크탑 1대)에서만 안전하게 접근할 수 있게 한다. 비용은 무료 범위 내로 유지한다.

## 접근 방식 결정

**Tailscale 무료 플랜**을 사용한다.

- 개인 계정 100대까지 무료
- iPadOS / Android / Windows / macOS 네이티브 앱 존재
- 앱이 공개 인터넷에 노출되지 않음 (공격 표면 최소화)
- 도메인 / TLS 인증서 / 포트 포워딩 불필요
- NAT 트래버설은 아웃바운드 UDP만 사용 → Oracle 인바운드 방화벽을 전부 닫아도 동작

### 대안과 비교

| 방식 | 비용 | 공격 표면 | 편의성 | 비고 |
|---|---|---|---|---|
| Tailscale | 무료 | 매우 작음 | 높음 (앱 설치 후 자동) | **선택** |
| Cloudflare Tunnel + Access | 무료 | 중간 (엣지는 공개) | 중간 | 도메인 필요 |
| Nginx + oauth2-proxy | 무료 | 큼 (443 공개) | 낮음 | 인증서/운영 부담 |

## 구성 개요

```
[iPad/Galaxy/노트북/데스크탑]
        │  Tailscale 앱 (Google 계정 로그인 + 2FA)
        ▼
   Tailnet (100.x.x.x, WireGuard)
        │
        ▼
[Oracle 컴퓨트 인스턴스]
  - Tailscale 데몬 (--ssh)
  - 인바운드 방화벽 전부 차단
  - 백엔드(FastAPI) / 프론트엔드는 Tailscale 인터페이스에만 바인딩
```

## 서버(Oracle) 구축 단계

### 1. 인스턴스 기본 세팅

- Ubuntu 22.04 / 24.04 Always Free shape (Ampere A1) 권장
- SSH 키 등록 후 최초 접속
- 기본 패키지 업데이트

### 2. Tailscale 설치 및 가입

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh --hostname=greed
```

- `--ssh` 플래그로 OpenSSH 대신 Tailscale SSH 사용 (22번 포트를 완전히 닫을 수 있음)
- 출력되는 URL을 브라우저에서 열어 Google 계정으로 승인
- Tailscale 관리 콘솔에서 해당 머신에 **"Disable key expiry"** 체크 (서버는 만료 없이 유지)

### 3. 앱 배포

- 백엔드 FastAPI: `uvicorn --host 100.x.x.x --port 8000` 또는 `--host 0.0.0.0`이되 아래 방화벽으로 차단
- 프론트엔드: 서빙 방식에 맞춰 동일하게 바인딩
- systemd 서비스로 등록해 재부팅 시 자동 기동

### 4. 방화벽 잠그기

**Oracle VCN Security List / NSG**
- 인바운드 규칙 전부 삭제 (0.0.0.0/0 허용 규칙 제거)
- 아웃바운드는 기본값 유지 (Tailscale이 아웃바운드로 연결 맺음)

**인스턴스 iptables (Ubuntu는 기본 ufw)**
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow in on tailscale0
sudo ufw enable
```

- `tailscale0` 인터페이스로 들어오는 트래픽만 허용
- 공인 IP로는 어떠한 포트도 응답하지 않음

## 클라이언트(5대 기기) 세팅

| 기기 | 앱 | 스토어 |
|---|---|---|
| iPad | Tailscale | App Store |
| Galaxy S23 | Tailscale | Play Store |
| 노트북 2대 / 데스크탑 1대 | Tailscale | 공식 사이트 (Windows/macOS 설치 파일) |

- 각 기기에서 동일한 Google 계정으로 로그인
- 접속은 브라우저에서 `http://greed:8000` (또는 할당된 hostname)
- MagicDNS는 관리 콘솔에서 켜두면 hostname 자동 해석

## 보안 강화 체크리스트

- [ ] Google 계정에 **2단계 인증(TOTP 또는 보안키)** 필수 설정 — Tailscale 인증의 최종 방어선
- [ ] Tailscale 관리 콘솔에서 **Device approval 활성화** — 새 기기 추가 시 관리자 승인 요구
- [ ] **ACL 정책**으로 5대 기기만 서버 접근 허용:
  ```json
  {
    "tagOwners": { "tag:server": ["autogroup:admin"] },
    "acls": [
      { "action": "accept", "src": ["autogroup:member"], "dst": ["tag:server:*"] }
    ],
    "ssh": [
      { "action": "accept", "src": ["autogroup:member"], "dst": ["tag:server"], "users": ["ubuntu", "root"] }
    ]
  }
  ```
- [ ] 서버 머신에 `tag:server` 태그 부여
- [ ] 정기적으로 관리 콘솔에서 기기 목록 점검
- [ ] 앱 자체 로그인(만약 있다면)은 그대로 유지 — 다중 방어선

## 운영 메모

- 무료 한도 초과 가능성: 개인 계정 100대 / 월 트래픽 제한 없음 → 해당 없음
- Tailscale 데몬 업데이트는 `sudo apt upgrade tailscale` 로 주기적으로 반영
- 외부에서 Tailscale 앱 없이 접속해야 할 일이 생기면 그때 Cloudflare Tunnel 병행 검토

## 참고

- Tailscale 공식 문서: https://tailscale.com/kb/
- Oracle Always Free 한도: https://www.oracle.com/cloud/free/
