# greed 개발 명세서

> 기준: 2026-04-21 현재 코드베이스 구현  
> 스택: FastAPI, SQLite, SQLAlchemy, React, TypeScript, Vite, Tailwind CSS  
> 배포 형태: 로컬 단일 머신

## 1. 시스템 개요

greed는 한국 주식 주봉 기술적 분석 결과를 로컬 DB에 저장하고 조회하는 관리 시스템이다. 데이터 생성은 스크리닝 스크립트와 에이전트 분석 흐름이 담당하고, 저장 및 조회는 FastAPI 백엔드와 React 프론트엔드가 담당한다.

```text
scripts/gogo2.py
  -> KOSPI/KOSDAQ 스크리닝
  -> pick_output/screening_YYYYMMDD.csv 저장
  -> 조건 충족 종목마다 scripts/pick.py run_pick() 호출
  -> pick_output/{ticker}_{name}_weekly_{YYYYMMDD}.csv 저장

AI 에이전트 또는 사용자
  -> CSV 기반 분석 마크다운 생성
  -> CLI 또는 Web UI로 백엔드 저장 요청

FastAPI
  -> 마크다운 재파싱
  -> SQLite 저장
  -> Run, Analysis, StockPrice 조회 API 제공

React Web UI
  -> 실행 목록, 실행별 분석 목록, 전체 분석 목록, 분석 상세 조회
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
│   ├── timezone.py
│   ├── cli.py
│   ├── routers/
│   │   ├── analyses.py
│   │   ├── jobs.py
│   │   ├── runs.py
│   │   └── stock.py
│   └── tests/
├── frontend/
│   └── src/
│       ├── api/
│       ├── components/
│       ├── constants/
│       ├── hooks/
│       ├── pages/
│       ├── types/
│       └── utils/
├── scripts/
│   ├── gogo2.py
│   ├── pick.py
│   └── dev.mjs
├── skills/
│   ├── install.bat
│   └── weekly-analysis/SKILL.md
├── pick_output/
├── docs/
├── greed.db
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

### 3-2. 데이터베이스

- DB 파일: `greed.db`
- DB URL: `sqlite:///greed.db`
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
| `model` | TEXT | 분석 모델명 |
| `markdown` | TEXT | 원본 분석 마크다운 |
| `judgment` | TEXT | `매수`, `홀드`, `매도` |
| `trend` | TEXT | `상승`, `하락`, `횡보` |
| `cloud_position` | TEXT | `구름 위`, `구름 안`, `구름 아래` |
| `ma_alignment` | TEXT | `정배열`, `역배열`, `혼조` |
| `entry_price` | REAL NULLABLE | 진입가 |
| `target_price` | REAL NULLABLE | 1차 목표가 |
| `stop_loss` | REAL NULLABLE | 손절가 |
| `created_at` | DATETIME | 생성 시각 |

인덱스: `run_id`, `ticker`, `judgment`

#### stock_prices

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `ticker` | TEXT PK | 종목 코드 |
| `price_date` | DATE | 가격 기준일 |
| `close_price` | REAL | 종가 |
| `fetched_at` | DATETIME | 조회 및 저장 시각 |

#### analysis_jobs

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `id` | INTEGER PK AUTOINCREMENT | 잡 ID |
| `ticker` | TEXT | 분석할 종목 코드 |
| `run_id` | INTEGER FK | 분석 결과가 저장될 실행 |
| `status` | TEXT | `pending`, `done`, `failed` |
| `error_message` | TEXT NULLABLE | 실패 단계와 사유 |
| `analysis_id` | INTEGER FK NULLABLE | 성공 시 생성된 분석 ID |
| `created_at` | DATETIME | 생성 시각 |

인덱스: `run_id`, `status`

## 4. 마크다운 파서

모듈: `backend/parser.py`

### 4-1. 필수 필드

| 필드 | 패턴 |
| --- | --- |
| `judgment` | `**매수**`, `**홀드**`, `**매도**` 우선. 볼드가 없으면 단독 줄의 `매수`, `홀드`, `매도`도 허용 |
| `trend` | `추세: 상승/하락/횡보` |
| `cloud_position` | `구름대 위치: 구름 위/구름 안/구름 아래` |
| `ma_alignment` | `MA 배열: 정배열/역배열/혼조` |

필수 필드 누락 시 `ParseResult.success`는 `False`이며, 누락 필드 목록은 `failed`에 담긴다.

### 4-2. 선택 가격 필드

| 필드 | 테이블 행 |
| --- | --- |
| `entry_price` | `진입 조건` 행의 가격대 |
| `target_price` | `1차 목표` 행의 가격대 |
| `stop_loss` | `손절 기준` 행의 가격대 |

- 가격은 정수 문자열만 추출한다.
- 쉼표와 `원` 단위는 허용한다.
- `53,000 ~ 55,000`처럼 범위 표기 시 첫 번째 숫자를 사용한다.
- `N/A`, `na`, `-`, `미정`, `없음`, `none`은 `NULL`로 처리한다.

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
| `GET` | `/analyses` | 전체 분석 목록. `judgment`, `run_id`, `q` 필터와 `page`, `page_size` 페이지네이션 지원 |
| `GET` | `/runs/{run_id}/analyses` | 특정 Run의 분석 목록. `judgment` 필터 지원 |
| `GET` | `/analyses/{analysis_id}` | 분석 상세 조회 |
| `GET` | `/analyses/{analysis_id}/history` | 동일 ticker 분석 이력 최신순 조회 |

`GET /analyses` 응답은 `{ items, page, page_size, total, total_pages }` 형태이며 기본 `page_size`는 25, 최대값은 100이다.

`POST /analyses` 요청은 스키마상 파싱 필드를 포함하지만, 서버는 `markdown`을 다시 파싱해 저장값을 덮어쓴다.

```json
{
  "run_id": 1,
  "ticker": "005930",
  "name": "삼성전자",
  "model": "GPT",
  "markdown": "...",
  "judgment": "보류",
  "trend": "보류",
  "cloud_position": "보류",
  "ma_alignment": "보류"
}
```

파싱 실패 응답:

```json
{
  "detail": "파싱 실패",
  "failed_fields": ["judgment", "cloud_position"]
}
```

### 5-3. Stock

| Method | Path | 설명 |
| --- | --- | --- |
| `GET` | `/stock/{ticker}/price` | 최근 종가 조회 및 캐시 |

- 당일 캐시가 있으면 DB 값을 반환한다.
- 캐시가 없으면 FinanceDataReader로 최근 10일 데이터를 조회하고 마지막 종가를 저장한다.
- 조회 실패 시 `404`와 `가격 데이터를 가져올 수 없습니다.`를 반환한다.

### 5-4. Jobs

| Method | Path | 설명 |
| --- | --- | --- |
| `POST` | `/jobs/trigger-analysis` | 티커 분석 잡 생성 및 백그라운드 실행 |
| `GET` | `/jobs/{job_id}` | 잡 상태 조회 |

`POST /jobs/trigger-analysis`

```json
{
  "ticker": "005930",
  "run_id": 1
}
```

성공 응답은 `202 Accepted`이며 `status`는 최초 `pending`이다. 백그라운드 작업은 job별 `pick_output/jobs/{job_id}/` 디렉터리에 주봉 CSV를 생성하고, Claude CLI에는 긴 CSV 프롬프트를 stdin으로 전달한다.

```json
{
  "id": 1,
  "ticker": "005930",
  "run_id": 1,
  "status": "pending",
  "error_message": null,
  "analysis_id": null,
  "created_at": "2026-04-21T20:00:00"
}
```

프론트엔드는 `GET /jobs/{job_id}`를 1~2초 간격으로 폴링한다. 성공 시 `status=done`과 `analysis_id`가 채워지고, 실패 시 `status=failed`와 `error_message`가 채워진다.

실패 메시지 접두사:

| 단계 | 형식 |
| --- | --- |
| `pick` | `pick: {예외 메시지}` 또는 `pick: CSV 파일 생성 안 됨` |
| `claude` | `claude: 180s 타임아웃 초과`, `claude: 빈 응답 반환`, `claude: {예외 메시지}` |
| `parser` | `parser: [필드명, ...] 필드 누락. 원본 앞 300자: ...` |
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
- 파일명 패턴이 `{ticker}_{name}_weekly_{YYYYMMDD}.md`이면 ticker와 name을 자동 추출한다.
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

- 단일 종목의 주봉 데이터를 추출한다.
- 직접 실행 시 기본 출력 디렉터리는 `./output`이다.
- `gogo2.py`에서 호출될 때는 `./pick_output`을 사용한다.

## 8. 프론트엔드

### 8-1. 라우팅

| Path | 페이지 | 상태 |
| --- | --- | --- |
| `/` | `/runs`로 리다이렉트 | 구현 |
| `/runs` | Run 목록 | 구현 |
| `/runs/:runId` | Run별 분석 목록 | 구현 |
| `/analyses` | 전체 분석 목록 | 구현 |
| `/analyses/:id` | 분석 상세 | 구현 |
| `/settings` | 플레이스홀더 | 저장 기능 미구현 |

### 8-2. 주요 화면

- `RunListPage`: 실행 목록, 새 실행 생성, 실행 상세 이동
- `StockListPage`: 실행별 분석 목록, 판정 필터, 수동 입력 모달
- `AnalysisListPage`: 전체 분석 목록, 판정 필터, Run ID 필터, 번호형 페이지네이션
- `AnalysisDetailPage`: 마크다운 렌더링, 핵심 지표, 가격 레벨, 동일 종목 이력, 티커 복사

### 8-3. 주요 컴포넌트

- `ManualInputModal`: 모델 선택, 실행 선택 또는 생성, ticker/name/markdown 입력, 파싱 미리보기, 저장
- `MarkdownRenderer`: `react-markdown`과 `remark-gfm` 기반 마크다운 렌더링
- `ParsedSummaryCard`: 필수 파싱 필드 성공 및 누락 상태 표시
- `PriceLevels`: 현재가 대비 목표가, 진입가, 손절가 차이 표시

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

> Windows에서 uvicorn `--reload` 시 `CTRL_C_EVENT`가 콘솔 세션 전체에 전파되어 통합 dev runner가 종료되는 문제로 인해 분리 실행 방식으로 전환.

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
- Analysis 저장, 필터링, 상세, 이력, 파싱 실패
- Markdown parser 필수 및 선택 필드 처리
- CLI 요청 payload, 파일명 파싱, 성공 및 실패 출력
- CRUD의 서울 시간 저장과 stock price upsert

권장 실행:

```bash
pytest backend/tests
```

## 11. 알려진 문서/구현 차이

- `skills/weekly-analysis/SKILL.md`는 현재 `scripts/pick_output/` 경로를 안내하지만, 스크립트 구현 기준 기본 산출물 위치는 프로젝트 루트의 `pick_output/`이다.
- 수동 입력 모달은 ticker와 name을 마크다운에서 자동 추출하지 않고 사용자가 직접 입력한다.
- 모델명은 백엔드에서 enum으로 제한하지 않는다. 프론트엔드는 `GPT`, `Gemini`, `Claude` 옵션을 제공하고 CLI는 임의 문자열을 전달할 수 있다.
