# GREED 인스턴스 배포 및 티커 분석 정상화 계획

## Summary
- 원격 인스턴스 `/home/opc/GREED`에 `origin/master`를 clone하고, 현재 로컬 `scripts/backtest/kospi200.csv` 수정분은 먼저 커밋 후 push해서 포함한다.
- 백엔드는 `systemd` 서비스로 `127.0.0.1:8000`, 프론트는 Vite dev 서버로 `0.0.0.0:5173`에 띄운다.
- MariaDB는 같은 인스턴스의 기존 `greed` DB와 `dbuser01` 계정을 사용한다. `.env`의 비밀번호는 로컬 `.env`에 있는 기존 `dbuser01` 비밀번호를 사용하되 출력하지 않는다.
- DB 데이터 이관은 사용자가 담당하고, 이후 내가 서비스 health, ticker 검색, 분석 job 생성/완료까지 검증한다.

## Key Changes
- 로컬 준비:
  - `scripts/backtest/kospi200.csv` 수정분을 커밋한다.
  - `git push origin master` 후 원격 인스턴스에서 같은 커밋을 clone한다.
- 원격 설치:
  - `/home/opc/GREED`에 repo clone.
  - `python3 -m venv .venv`
  - `.venv/bin/python -m pip install -U pip`
  - `.venv/bin/pip install -r backend/requirements.txt -r scripts/requirements.txt`
  - `cd frontend && npm ci`
- 원격 `.env`:
  - `/home/opc/GREED/.env` 생성.
  - `DATABASE_URL=mysql+pymysql://dbuser01:<local-.env-password>@127.0.0.1:3306/greed?charset=utf8mb4`
  - `CORS_ORIGIN=http://146.56.170.98:5173`
- systemd 서비스:
  - `greed-backend.service`
    - `User=opc`
    - `WorkingDirectory=/home/opc/GREED`
    - `Environment=HOME=/home/opc`
    - `Environment=PATH=/usr/local/bin:/usr/bin:/bin:/home/opc/.local/bin`
    - `ExecStart=/home/opc/GREED/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`
    - `Restart=always`
  - `greed-frontend.service`
    - `User=opc`
    - `WorkingDirectory=/home/opc/GREED/frontend`
    - `ExecStart=/usr/bin/npm run dev -- --host 0.0.0.0 --port 5173`
    - `Restart=always`
- 네트워크:
  - 인스턴스 firewalld에 `5173/tcp`를 permanent open 후 reload.
  - `8000`은 외부 공개하지 않고 Vite proxy(`/api -> 127.0.0.1:8000`)로만 사용한다.
  - 외부 브라우저에서 `http://146.56.170.98:5173` 접속을 목표로 한다.

## Ticker Analysis
- CLI 확인:
  - 이미 원격 PATH에서 `claude`, `codex`, `gemini`는 확인됨.
  - Gemini는 현재 backend 명령 형태와 같은 headless 호출이 응답하는 것까지 확인됨.
  - 실행 시 `claude`, `codex`, `gemini` 각각 짧은 파일 생성 smoke test를 수행한다.
- 호환성 처리:
  - Codex smoke test에서 `codex exec --yolo -`가 실패하면 `backend/routers/jobs.py`의 `_codex_cmd()`를 현재 CLI 옵션인 `codex exec --dangerously-bypass-approvals-and-sandbox -`로 바꾸고 테스트한다.
  - Gemini 모델명 또는 옵션 실패가 있으면 `_gemini_cmd()`만 수정하고, 프론트/스키마는 건드리지 않는다.
- DB 이관 후 검증:
  - `GET /api/health`가 `database.status=up`인지 확인.
  - ticker table이 비어 있거나 검색이 실패하면 `python scripts/refresh_tickers.py`로 KRX/US ticker 목록을 갱신한다.
  - UI 또는 API로 run 생성 후 `005930` 분석 job을 `claude` 모델로 1건 실행한다.
  - `pick_output/jobs/{job_id}/prompt.md`, CSV, `analysis.md`, `exit_code.txt` 생성과 job `done`, `analysis_id` 연결을 확인한다.
  - 이후 `codex`, `gemini`도 각 1건씩 같은 방식으로 확인한다.

## Test Plan
- Backend:
  - `.venv/bin/python -m pytest backend/tests -q`
  - `.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`
  - `curl http://127.0.0.1:8000/api/health`
- Frontend:
  - `cd frontend && npm run build`
  - `systemctl status greed-frontend greed-backend`
  - `curl -I http://127.0.0.1:5173`
  - 로컬 브라우저에서 `http://146.56.170.98:5173`
- Analysis acceptance:
  - run 생성, ticker 검색, analysis job 생성, job 완료, 분석 상세 화면 이동까지 확인한다.
  - 실패 시 `journalctl -u greed-backend -n 200`, `pick_output/jobs/{job_id}/stderr.log`, `stdout.log` 순서로 원인을 본다.

## Assumptions
- DB 스키마/데이터 이관은 사용자가 완료한다.
- 원격 MariaDB의 DB명은 `greed`, 앱 계정은 `dbuser01`을 사용한다.
- `dbuser01` 비밀번호는 로컬 `.env`의 기존 값을 사용한다.
- 외부 접속이 firewalld 개방 후에도 안 되면 OCI 보안 목록/NSG에서 `5173/tcp` 인바운드도 열어야 한다.
