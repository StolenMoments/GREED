# greed 개발 명세서

> 기준: 2026-05-07 현재 코드베이스 구현
> 스택: FastAPI, MariaDB, SQLAlchemy, React, TypeScript, Vite, Tailwind CSS
> 배포 형태: 로컬 단일 머신

## 1. 시스템 개요

greed는 한국/미국 주식의 주봉 기술적 분석 결과를 로컬 DB에 저장하고 조회하는 관리 시스템이다. 데이터 생성은 스크리닝 및 주봉 CSV 생성 스크립트가 담당하고, 분석 저장/조회/비동기 분석 잡 관리는 FastAPI 백엔드와 React 프론트엔드가 담당한다.

```text
scripts/gogo2.py
  -> KOSPI/KOSDAQ 스크리닝
  -> pick_output/screening_YYYYMMDD.csv 저장
  -> 조건 충족 종목마다 scripts/pick.py run_pick() 호출
  -> pick_output/{market}_{ticker}_{name}_weekly_{YYYYMMDD}.csv 저장

scripts/pick.py / scripts/pick_us.py
  -> 단일 한국/미국 종목 주봉 CSV 생성
  -> 일목균형표, 이동평균, 거래량, 변동성, 모멘텀 지표 포함

FastAPI
  -> Run, Analysis, Job, StockPrice, Ticker 조회 API 제공
  -> 마크다운 재파싱 후 MariaDB 저장
  -> 모델 CLI 기반 비동기 분석 잡 실행 및 상태 확정

React Web UI
  -> 실행 목록, 실행별 분석 목록, 전체 분석 목록, 분석 상세, 잡 목록, 종목 요약 조회
  -> 종목 검색 기반 분석 트리거와 수동 분석 입력 제공
```

## 2. 디렉터리 구조

```text
greed/
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── crud.py
│   ├── parser.py
│   ├── stock_price.py
│   ├── tickers.py
│   ├── timezone.py
│   ├── cli.py
│   ├── routers/
│   │   ├── analyses.py
│   │   ├── jobs.py
│   │   ├── runs.py
│   │   ├── stock.py
│   │   ├── stocks.py
│   │   └── tickers.py
│   └── tests/
├── frontend/
│   └── src/
│       ├── api/
│       ├── components/
│       ├── constants/
│       ├── contexts/
│       ├── hooks/
│       ├── pages/
│       ├── types/
│       └── utils/
├── scripts/
│   ├── gogo2.py
│   ├── pick.py
│   ├── pick_us.py
│   ├── refresh_tickers.py
│   └── fdr_timeout.py
├── skills/
│   └── weekly-analysis/SKILL.md
├── pick_output/
├── docs/
├── package.json
└── install.bat
```

## 3. 백엔드

### 3-1. 애플리케이션

- 엔트리포인트: `backend/main.py`
- FastAPI 앱 이름: `Greed API`
- 시작 시 `init_db()`로 SQLAlchemy 모델 기반 테이블을 생성한다.
- CORS 기본 허용 출처는 `http://localhost:5173`이다.
- `CORS_ORIGIN` 환경변수로 허용 출처를 변경할 수 있다.
- 등록 라우터: `runs`, `analyses`, `stock`, `stocks`, `jobs`, `tickers`

### 3-2. 데이터베이스

- DB: MariaDB
- DB URL: 환경변수 `DATABASE_URL` 필수 (예: `mysql+pymysql://user:pass@host:3306/greed?charset=utf8mb4`)
- SQLAlchemy ORM을 사용한다.
- 생성 및 조회 시각은 `backend/timezone.py`의 `seoul_now()`를 통해 `Asia/Seoul` 기준으로 기록한다.

### 3-3. 테이블

#### runs

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `id` | INTEGER PK AUTOINCREMENT | 실행 ID |
| `memo` | TEXT NULLABLE | 메모 |
| `created_at` | DATETIME | 생성 시각 |

#### analyses

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `id` | INTEGER PK AUTOINCREMENT | 분석 ID |
| `run_id` | INTEGER FK | 소속 실행 |
| `ticker` | TEXT | 종목 코드 |
| `name` | TEXT | 종목명 |
| `name_initials` | TEXT | 종목명 초성 검색용 값 |
| `model` | TEXT | 분석 모델명 |
| `markdown` | TEXT | 원본 분석 마크다운 |
| `judgment` | TEXT | `매수`, `홀드`, `매도` |
| `trend` | TEXT | `상승`, `하락`, `횡보` |
| `cloud_position` | TEXT | `구름 위`, `구름 안`, `구름 아래` |
| `ma_alignment` | TEXT | `정배열`, `역배열`, `혼조` |
| `entry_price` | REAL NULLABLE | 진입가 하단 |
| `entry_price_max` | REAL NULLABLE | 진입가 상단 |
| `target_price` | REAL NULLABLE | 1차 목표가 하단 |
| `target_price_max` | REAL NULLABLE | 1차 목표가 상단 |
| `stop_loss` | REAL NULLABLE | 손절가 하단 |
| `stop_loss_max` | REAL NULLABLE | 손절가 상단 |
| `created_at` | DATETIME | 생성 시각 |

인덱스: `run_id`, `ticker`, `judgment`, `name_initials`

#### analysis_jobs

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `id` | INTEGER PK AUTOINCREMENT | 잡 ID |
| `ticker` | TEXT | 분석할 종목 코드 |
| `run_id` | INTEGER FK | 분석 결과가 저장될 실행 |
| `model` | TEXT | 실행할 모델 CLI 선택값. 기본값 `claude` |
| `status` | TEXT | `pending`, `done`, `failed` |
| `error_message` | TEXT NULLABLE | 실패 단계와 사유 |
| `raw_markdown` | TEXT NULLABLE | 파싱 성공/실패 시 읽은 원본 분석 마크다운 |
| `analysis_id` | INTEGER FK NULLABLE | 성공 시 생성된 분석 ID |
| `created_at` | DATETIME | 생성 시각 |

인덱스: `run_id`, `status`

#### stock_prices

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `ticker` | TEXT PK | 종목 코드 |
| `price_date` | DATE | 가격 기준일 |
| `close_price` | REAL | 종가 |
| `fetched_at` | DATETIME | 조회 및 저장 시각 |

#### krx_stocks

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `code` | TEXT PK | 6자리 한국 종목 코드 |
| `name` | TEXT | 종목명 |
| `name_initials` | TEXT | 초성 검색용 값 |
| `updated_at` | DATETIME | 갱신 시각 |

인덱스: `name`, `name_initials`

#### us_stocks

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `code` | TEXT PK | 미국 티커 |
| `name` | TEXT | 종목명 |
| `market` | TEXT | `NASDAQ`, `NYSE`, `AMEX` 등 |
| `updated_at` | DATETIME | 갱신 시각 |

인덱스: `name`, `market`

## 4. 마크다운 파서

모듈: `backend/parser.py`

### 4-1. 필수 필드

| 필드 | 패턴 |
| --- | --- |
| `judgment` | `**매수**`, `**홀드**`, `**매도**` 우선. 볼드가 없으면 단독 줄의 `매수`, `홀드`, `매도`도 허용 |
| `trend` | `추세: 상승/하락/횡보` |
| `cloud_position` | `구름대 위치: 구름 위/구름 안/구름 아래` |
| `ma_alignment` | `MA 배열: 정배열/역배열/혼조` |

필수 필드 누락 또는 가격 관계 검증 실패 시 `ParseResult.success`는 `False`이며, 누락/실패 필드 목록은 `failed`에 담긴다.

### 4-2. 선택 가격 필드

| 필드 | 테이블 행 |
| --- | --- |
| `entry_price`, `entry_price_max` | `진입`이 포함된 행의 가격대. 눌림/돌파 진입 행을 모두 허용 |
| `target_price`, `target_price_max` | `1차 목표` 행의 가격대 |
| `stop_loss`, `stop_loss_max` | `손절 기준` 행의 가격대 |

- 가격은 정수 또는 소수 문자열을 추출한다.
- 쉼표와 원/달러 단위는 허용한다.
- `53,000 ~ 55,000`처럼 범위 표기 시 최소값과 최대값을 함께 저장한다.
- `N/A`, `na`, `-`, `미정`, `없음`, `none`은 `NULL`로 처리한다.
- `매수` 또는 `홀드` 판정에서 목표가 상단이 진입가 상단보다 낮거나 손절가가 진입가 하단보다 높으면 `price_consistency` 실패로 처리한다.

### 4-3. 진입 후보

- `parse_entry_candidates()`는 마크다운 표에서 `진입`이 포함된 행을 읽어 후보 목록을 만든다.
- 행 이름에 `눌림`이 있으면 후보 라벨은 `눌림`, `돌파`가 있으면 `돌파`, 둘 다 없으면 `진입`이다.
- 후보 가격 범위와 현재가가 함께 있으면 현재가 대비 괴리율을 계산해 분석 목록 필터와 정렬에 사용한다.

## 5. API 명세

Base URL: `http://localhost:8000/api`

### 5-1. Runs

| Method | Path | 설명 |
| --- | --- | --- |
| `POST` | `/runs` | Run 생성 |
| `GET` | `/runs` | Run 목록 조회. 분석 개수 포함 |
| `GET` | `/runs/{run_id}` | Run 단건 조회. 분석 개수 포함 |

`POST /runs`

```json
{ "memo": "optional memo" }
```

### 5-2. Analyses

| Method | Path | 설명 |
| --- | --- | --- |
| `POST` | `/analyses` | 분석 저장. 서버에서 마크다운 재파싱 |
| `GET` | `/analyses` | 전체 분석 목록. `judgment`, `run_id`, `q`, `entry_gap_lte`, `entry_candidate` 필터와 `page`, `page_size` 페이지네이션 지원 |
| `GET` | `/runs/{run_id}/analyses` | 특정 Run의 분석 목록. `judgment` 필터 지원 |
| `GET` | `/analyses/{analysis_id}` | 분석 상세 조회 |
| `GET` | `/analyses/{analysis_id}/history` | 동일 ticker 분석 이력 최신순 조회 |

`GET /analyses` 응답은 `{ items, page, page_size, total, total_pages }` 형태이며 기본 `page_size`는 25, 최대값은 100이다. `q`는 티커, 종목명, 종목명 초성을 검색한다. `entry_candidate`는 `all`, `pullback`, `breakout` 중 하나이며 `entry_gap_lte`와 함께 진입가 근접 분석 필터에 사용한다.

분석 요약 응답 주요 필드:

```json
{
  "id": 1,
  "run_id": 1,
  "ticker": "005930",
  "name": "삼성전자",
  "model": "claude-code",
  "judgment": "매수",
  "trend": "상승",
  "cloud_position": "구름 위",
  "ma_alignment": "정배열",
  "entry_price": 53000,
  "entry_price_max": 55000,
  "target_price": 65000,
  "target_price_max": null,
  "stop_loss": 50000,
  "stop_loss_max": null,
  "current_price": 54000,
  "current_price_date": "2026-05-07",
  "entry_gap_pct": 0,
  "is_entry_near": true,
  "entry_candidates": [
    {
      "label": "눌림",
      "price": 53000,
      "price_max": 55000,
      "gap_pct": 0,
      "is_near": true
    }
  ]
}
```

`POST /analyses` 요청은 스키마상 파싱 필드를 포함하지만, 서버는 `markdown`을 다시 파싱해 저장값을 덮어쓴다.

```json
{
  "run_id": 1,
  "ticker": "005930",
  "name": "삼성전자",
  "model": "GPT",
  "markdown": "...",
  "judgment": "홀드",
  "trend": "횡보",
  "cloud_position": "구름 안",
  "ma_alignment": "혼조"
}
```

파싱 실패 응답:

```json
{
  "detail": "파싱 실패",
  "failed_fields": ["judgment", "cloud_position"]
}
```

### 5-3. Stock Price

| Method | Path | 설명 |
| --- | --- | --- |
| `GET` | `/stock/{ticker}/price` | 최근 종가 조회 및 캐시 |
| `POST` | `/stock/{ticker}/price/refresh` | 캐시 여부와 관계없이 최근 종가 재조회 후 저장 |

- 티커는 서버에서 정규화한다. 숫자 티커는 6자리로 zero-padding한다.
- `GET`은 당일 캐시가 있으면 DB 값을 반환한다.
- 캐시가 없거나 `refresh` 요청이면 FinanceDataReader로 최근 종가를 조회해 저장한다.
- 조회 실패 시 `404`와 `가격 데이터를 가져올 수 없습니다.`를 반환한다.

### 5-4. Stocks

| Method | Path | 설명 |
| --- | --- | --- |
| `GET` | `/stocks/summary` | 분석이 저장된 종목별 매수/홀드/매도 개수와 최신 분석 시각 조회 |

응답 항목:

```json
{
  "ticker": "005930",
  "name": "삼성전자",
  "name_initials": "ㅅㅅㅈㅈ",
  "buy_count": 2,
  "hold_count": 1,
  "sell_count": 0,
  "latest_at": "2026-05-07T16:00:00"
}
```

### 5-5. Tickers

| Method | Path | 설명 |
| --- | --- | --- |
| `GET` | `/tickers/search?q=...` | KRX/US 종목 검색. 최대 10개 반환 |
| `GET` | `/tickers/{code}` | 단일 티커 조회 |

- KRX 검색은 종목명, 초성, 코드 기반으로 동작한다.
- US 검색은 티커와 종목명 기반으로 동작한다.
- 영문 검색어는 KRX 일부와 US 결과를 함께 반환한다.
- 숫자 티커는 6자리 한국 종목 코드로 정규화한다.

### 5-6. Jobs

| Method | Path | 설명 |
| --- | --- | --- |
| `POST` | `/jobs/trigger-analysis` | 티커 분석 잡 생성 및 모델 프로세스 시작 |
| `GET` | `/jobs?run_id=...&status=pending&status=failed` | 잡 목록 조회. 실행 ID와 상태 필터 지원 |
| `GET` | `/jobs/{job_id}` | 잡 상태 조회 및 pending 잡 확정 처리 |

`POST /jobs/trigger-analysis`

```json
{
  "ticker": "005930",
  "run_id": 1,
  "model": "claude"
}
```

- `model` 허용 UI 값은 `claude`, `codex`, `agy`이며 백엔드 기본값은 `claude`이다.
- `ticker`는 코드, 미국 티커, 한국 종목명/초성 검색 결과를 받을 수 있다.
- 성공 응답은 `202 Accepted`이며 `status`는 최초 `pending`이다.
- 한국 종목은 `scripts/pick.py`, 미국 종목은 `scripts/pick_us.py`로 주봉 CSV를 만든다.
- 당일 동일 티커 CSV는 `pick_output/chart_cache/{YYYYMMDD}/`에서 재사용하고, job별 산출물은 `pick_output/jobs/{job_id}/`에 복사한다.
- 모델별 실행기는 `claude-code`, `codex-cli`, `agy` 분석 결과를 `analysis.md` 파일에 저장하도록 프롬프트를 만든다.
- Windows에서는 가능한 경우 배치 래퍼 대신 실제 실행 파일 또는 node 엔트리포인트를 호출해 stdin/exit code 문제를 줄인다.

job 산출물:

| 파일 | 설명 |
| --- | --- |
| `prompt.md` | 모델에 전달한 최종 프롬프트 |
| `analysis.md` | 모델이 저장해야 하는 최종 분석 마크다운 |
| `stdout.log` | 모델 프로세스 stdout |
| `stderr.log` | 모델 프로세스 stderr |
| `model.pid` | 감시 프로세스 PID |
| `exit_code.txt` | 모델 프로세스 종료 코드 |

pending job 조회 시 백엔드는 job별 lock을 잡고 최신 상태를 다시 읽은 뒤 `analysis.md`, `exit_code.txt`, PID, 생성 시각을 확인한다. `analysis.md`가 존재하고 비어 있지 않으면 마크다운을 파싱해 `analyses`에 한 번만 저장한 뒤 `status=done`과 `analysis_id`를 채운다. 모델 CLI가 `analysis.md` 없이 종료되면 `model_exit`, 시작 추적이 실패하면 `model_start`, 기본 30분을 넘기면 `timeout` 실패로 전환한다.

실패 메시지 접두사:

| 단계 | 형식 |
| --- | --- |
| `pick` | `pick: {예외 메시지}` 또는 `pick: CSV 파일 생성 안 됨` |
| `model_start` | `model_start: {model}: {예외 메시지}` |
| `model_exit` | `model_exit: {model}: exit_code={code}; analysis.md was not created; ...` |
| `parser` | `parser: [필드명, ...] 필드 누락. 원본 앞 300자: ...` |
| `timeout` | `timeout: {model}: analysis.md 생성 시간 초과` |
| `db` | `db: {예외 메시지}` |

## 6. CLI

모듈: `backend/cli.py`

```bash
python -m backend.cli --api-base-url http://localhost:8000/api run create --memo "memo"
python -m backend.cli analysis save --run-id 1 --ticker 005930 --name 삼성전자 --model GPT --file analysis.md
python -m backend.cli analysis save-dir --run-id 1 --model GPT --dir analyses
```

- 기본 API base URL은 `http://localhost:8000/api`이다.
- `run create`는 생성된 Run ID만 출력한다.
- `analysis save-dir`는 `*.md` 파일을 정렬해 순회한다.
- 파일명 패턴이 `{market}_{ticker}_{name}_weekly_{YYYYMMDD}.md`, `{ticker}_{market}_{name}_weekly_{YYYYMMDD}.md`, 또는 `{ticker}_{name}_weekly_{YYYYMMDD}.md`이면 ticker와 name을 자동 추출한다.
- 이름에 `_`가 포함되어도 `_weekly_YYYYMMDD` 앞까지 name으로 처리한다.

## 7. 스크립트

### 7-1. gogo2.py

```bash
python scripts/gogo2.py
python scripts/gogo2.py --candle 10 --ma 5 --gc 5 --workers 10 --batch 50 --weeks 160 --restart
```

- KOSPI, KOSDAQ을 대상으로 스크리닝한다.
- 기본 조회 기간은 160주이다.
- 결과와 진행 상태는 `pick_output/`에 저장한다.
- 조건 충족 종목은 자동으로 `pick.run_pick()`에 전달되어 5년치 주봉 CSV가 생성된다.

### 7-2. pick.py

```bash
python scripts/pick.py 005930 --years 5 --output ./pick_output
```

- 한국 단일 종목의 주봉 데이터를 추출한다.
- 직접 실행 시 기본 출력 디렉터리는 `./output`이다.
- `gogo2.py`와 jobs 파이프라인에서는 별도 출력 디렉터리를 전달한다.

### 7-3. pick_us.py

```bash
python scripts/pick_us.py AAPL
python scripts/pick_us.py NVDA --years 5 --output ./pick_output
```

- 미국 단일 종목의 주봉 데이터를 추출한다.
- NASDAQ/NYSE/AMEX listing에서 종목명을 조회한다.
- 미국 주봉은 금요일 기준 `W-FRI`로 집계한다.
- `--no-future-cloud` 옵션으로 미래 구름 26주 행을 제외할 수 있다.

### 7-4. refresh_tickers.py

```bash
python scripts/refresh_tickers.py
python scripts/refresh_tickers.py --krx
python scripts/refresh_tickers.py --us
```

- FinanceDataReader에서 KRX/US 종목 목록을 가져와 `krx_stocks`, `us_stocks` 테이블을 갱신한다.
- KRX 종목은 초성 검색용 `name_initials`를 함께 저장한다.

## 8. 프론트엔드

### 8-1. 라우팅

| Path | 페이지 | 상태 |
| --- | --- | --- |
| `/` | `/runs`로 리다이렉트 | 구현 |
| `/runs` | Run 목록 | 구현 |
| `/runs/:runId` | Run별 분석 목록 및 분석 트리거 | 구현 |
| `/analyses` | 전체 분석 목록 | 구현 |
| `/analyses/:id` | 분석 상세 | 구현 |
| `/jobs` | 잡 목록 | 구현 |
| `/stocks` | 종목별 요약 | 구현 |

### 8-2. 주요 화면

- `RunListPage`: 실행 목록, 새 실행 생성, 실행 상세 이동
- `StockListPage`: 실행별 분석 목록, 판정 필터, 종목 검색 기반 비동기 분석 트리거, 수동 입력 모달
- `AnalysisListPage`: 전체 분석 목록, 판정/Run ID/검색어/진입가 근접 필터, 페이지네이션
- `AnalysisDetailPage`: 마크다운 렌더링, 핵심 지표, 가격 레벨, 동일 종목 이력, 티커 복사, 빠른 재분석
- `JobsPage`: 전체 job 목록, pending/failed 집계, 상태 필터, 완료 분석 상세 이동
- `StockSummaryPage`: 종목별 매수/홀드/매도 집계, 검색, 정렬, 종목별 분석 목록 이동

### 8-3. 주요 컴포넌트

- `TickerAnalysisForm`: 종목명/티커 검색, 모델 선택, 비동기 분석 잡 생성, 완료 분석 이동
- `QuickAnalysisLauncher`: 상세 화면에서 동일 종목을 현재 run에 다시 분석
- `ManualInputModal`: 모델 선택, 실행 선택 또는 생성, ticker/name/markdown 입력, 파싱 미리보기, 저장
- `AnalysisTable`: 분석 목록 표시, 진입가 괴리율과 진입 후보 표시
- `MarkdownRenderer`: `react-markdown`과 `remark-gfm` 기반 마크다운 렌더링
- `ParsedSummaryCard`: 필수 파싱 필드 성공 및 누락 상태 표시
- `PriceLevels`: 현재가 대비 목표가, 진입가, 손절가 차이 표시와 가격 refresh
- `PendingJobsContext`: 생성된 job을 폴링하고 완료/실패 시 목록 캐시를 갱신

## 9. 개발 실행

터미널 두 개를 열어 루트에서 각각 실행:

```bash
# 터미널 1 - 백엔드
npm run back

# 터미널 2 - 프론트엔드
npm run front
```

- 백엔드: `python.exe -m uvicorn backend.main:app --reload`
- 프론트엔드: `vite --host 127.0.0.1 --port 5173`

프론트엔드만 실행:

```bash
cd frontend
npm run dev
npm run build
```

## 10. 테스트

백엔드 테스트는 `backend/tests/`에 있으며 다음 영역을 검증한다.

- FastAPI 라우트 등록 및 CORS
- Run 생성, 조회, 분석 개수 집계
- Analysis 저장, 필터링, 상세, 이력, 파싱 실패, 진입가 근접 필터
- Markdown parser 필수/선택/가격 범위/가격 관계 처리
- Jobs 생성, 상태 조회, 모델 실행 실패/성공 확정, ticker 정규화
- Stock price 조회 및 refresh, 종목 요약, ticker 검색
- CLI 요청 payload, 파일명 파싱, 성공 및 실패 출력
- KRX/US picker 지표 생성 일부

권장 실행:

```bash
pytest backend/tests
```

프론트엔드 빌드:

```bash
cd frontend
npm run build
```

## 11. 알려진 문서/구현 차이

- `skills/weekly-analysis/SKILL.md`는 `scripts/pick_output/` 경로를 안내하지만, 스크립트 구현 기준 기본 산출물 위치는 프로젝트 루트의 `pick_output/`이다.
- 수동 입력 모달은 ticker와 name을 마크다운에서 자동 추출하지 않고 사용자가 직접 입력한다.
- 수동 입력 모달의 모델 표기는 `GPT`, `Antigravity`, `Claude`이고, 비동기 분석 잡의 모델 값은 `claude`, `codex`, `agy`이다.
