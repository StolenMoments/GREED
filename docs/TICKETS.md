# GREED — JIRA 티켓 초안

> 프로젝트 키: **GREED**  
> 형식: Confluence 491561 (Jira 티켓 작성 가이드라인) 준수  
> 의존성: `초기 설정 → DB/Entity → Schema/CRUD → Parser/Router → Main → CLI → FE`

---

## Phase 0 — SKILL 배포

---

### GREED-1 · [INFRA] weekly-analysis SKILL.md 및 배포 스크립트 작성

**선행 작업:** 없음

**작업 내용**
- `skills/weekly-analysis/SKILL.md` 작성 (DEV_SPEC.md §4-2 내용 전문 수록)
  - 사전 조건 확인 (백엔드 응답, pick_output 존재 여부)
  - Step 1~5 실행 절차 (Run 생성 → CSV 수집 → 분석 → API 저장 → 완료 보고)
  - 분석 지침 SYSTEM 프롬프트 (일목구름 해석, MA 배열, 출력 형식 5개 섹션)
  - 에이전트별 컨텍스트 용량 기준 표
- `skills/install.sh` 작성 (Codex CLI 글로벌 원본 배치 + Claude/Gemini symlink)
- `skills/install.bat` 작성 (Windows mklink → hardlink → copy 폴백 로직)

**완료 조건**
- `bash skills/install.sh` 실행 시 오류 없이 완료
- `~/.claude/skills/weekly-analysis/SKILL.md` 파일 존재 확인
- Claude Code에서 `/weekly-analysis` 스킬 로드 확인

---

## Phase 1 — Backend Core

---

### GREED-2 · [DB] runs/analyses 테이블 DDL 및 SQLAlchemy 모델 작성

**선행 작업:** 없음

**작업 내용**
- `backend/database.py`: SQLAlchemy `create_engine`, `SessionLocal`, `Base` 설정 (SQLite `greed.db`)
- `backend/models.py`: `Run`, `Analysis` ORM 모델 정의
  - `Run`: `id`, `memo`, `created_at`
  - `Analysis`: `id`, `run_id(FK)`, `ticker`, `name`, `model`, `markdown`, `judgment`, `trend`, `cloud_position`, `ma_alignment`, `entry_price`, `target_price`, `stop_loss`, `created_at`
  - 인덱스: `(run_id)`, `(ticker)`, `(judgment)`
- `backend/database.py`에 `Base.metadata.create_all()` 호출로 테이블 자동 생성

**완료 조건**
- `python -c "from backend.database import engine; from backend.models import Base; Base.metadata.create_all(engine)"` 실행 후 `greed.db` 생성 확인
- SQLite CLI로 `runs`, `analyses` 테이블 스키마 확인 (`.schema runs`, `.schema analyses`)
- `analyses.run_id` FK 제약 및 인덱스 3개 존재 확인

---

### GREED-3 · [BE] Pydantic 스키마(schemas.py) 및 CRUD 레이어(crud.py) 구현

**선행 작업:** GREED-2

**작업 내용**
- `backend/schemas.py`: Pydantic v2 모델 정의
  - `RunCreate`, `RunRead` (id, memo, created_at, analysis_count)
  - `AnalysisCreate` (run_id, ticker, name, model, markdown)
  - `AnalysisRead` (전체 필드), `AnalysisSummary` (목록용 요약)
- `backend/crud.py`: DB 조작 함수
  - `create_run(db, memo)` → `Run`
  - `get_runs(db)` → `list[Run]` (analysis_count 포함)
  - `get_run(db, run_id)` → `Run | None`
  - `create_analysis(db, obj)` → `Analysis`
  - `get_analyses_by_run(db, run_id, judgment=None)` → `list[Analysis]`
  - `get_analysis(db, id)` → `Analysis | None`
  - `get_analysis_history(db, ticker)` → `list[Analysis]`

**완료 조건**
- `pytest backend/tests/test_crud.py` 통과
  - `create_run` → DB에 행 삽입 확인
  - `get_runs` → analysis_count 정확성 확인
  - `get_analyses_by_run` + judgment 필터 동작 확인
  - `get_analysis_history` → 동일 ticker 이력 정렬 확인

---

### GREED-4 · [BE] parser.py 마크다운 파싱 모듈 구현

**선행 작업:** GREED-2

**작업 내용**
- `backend/parser.py`: `parse_markdown(markdown: str) -> ParseResult` 함수 구현
- `ParseResult` dataclass: `data: dict`, `failed: list[str]`, `success: bool`
- 파싱 대상 필드 및 정규식 (DEV_SPEC.md §6-1 준수):
  - 필수: `judgment`, `trend`, `cloud_position`, `ma_alignment`
  - 선택: `entry_price`, `target_price`, `stop_loss`
- 엣지케이스 처리 (DEV_SPEC.md §12):
  - 가격 범위 표기(`53,000 ~ 55,000`) → 하한값 사용
  - 가격에 단위 포함(`75,000원`) → 숫자만 추출
  - 볼드 없는 판정(`매수`) → fallback 패턴 적용
  - `N/A`, `-`, `미정` → `None` 반환 (선택 필드)

**완료 조건**
- `pytest backend/tests/test_parser.py` 통과
  - 정상 마크다운 → `success=True`, 전체 필드 파싱 확인
  - 판정 누락 마크다운 → `success=False`, `failed=['judgment']` 확인
  - 가격 범위 표기 → 하한값 반환 확인
  - `N/A` 입력 → `None` 반환 확인
  - fallback 패턴(볼드 없는 판정) → 정상 파싱 확인

---

### GREED-5 · [BE] routers/runs.py — runs API 엔드포인트 구현

**선행 작업:** GREED-3

**작업 내용**
- `backend/routers/runs.py`: FastAPI APIRouter (`prefix="/api/runs"`) 구현
  - `POST /api/runs` → `RunCreate` 수신, `RunRead` 반환 (201)
  - `GET /api/runs` → `list[RunRead]` 반환, 각 항목에 `analysis_count` 포함
  - `GET /api/runs/{run_id}` → `RunRead` 반환, 없으면 404

**완료 조건**
- `pytest backend/tests/test_runs_router.py` 통과 (TestClient 사용)
  - `POST /api/runs` → 201, 응답 body에 `id`, `created_at` 존재 확인
  - `GET /api/runs` → 200, list 형태 응답 확인
  - `GET /api/runs/999` → 404 확인

---

### GREED-6 · [BE] routers/analyses.py — analyses API 엔드포인트 구현

**선행 작업:** GREED-3, GREED-4, GREED-5

**작업 내용**
- `backend/routers/analyses.py`: FastAPI APIRouter 구현
  - `POST /api/analyses` → `AnalysisCreate` 수신 → `parser.parse_markdown()` 호출 → DB 저장 → `AnalysisRead` 반환 (201)
    - 파싱 필수 필드 실패 시 `422 {"detail":"파싱 실패","failed_fields":[...]}` 반환
  - `GET /api/analyses` → 전체 분석 최신순 `list[AnalysisSummary]` 반환 (`?judgment=매수&run_id=1` 필터 지원)
  - `GET /api/runs/{run_id}/analyses` → `list[AnalysisSummary]` 반환 (`?judgment=매수` 필터 지원)
  - `GET /api/analyses/{id}` → `AnalysisRead` 반환, 없으면 404
  - `GET /api/analyses/{id}/history` → 동일 ticker의 `list[AnalysisSummary]` 반환 (최신순)

**완료 조건**
- `pytest backend/tests/test_analyses_router.py` 통과
  - `POST /api/analyses` 정상 마크다운 → 201, `judgment` 필드 파싱값 응답 확인
  - `POST /api/analyses` 판정 누락 마크다운 → `422`, `failed_fields` 포함 확인
  - `GET /api/analyses?judgment=매수` → 전체 분석 중 매수 판정만 최신순 반환 확인
  - `GET /api/runs/{run_id}/analyses?judgment=매수` → 매수 판정만 반환 확인
  - `GET /api/analyses/{id}/history` → 동일 ticker 이력 최신순 정렬 확인

---

### GREED-7 · [BE] main.py FastAPI 앱 진입점 및 CORS 설정

**선행 작업:** GREED-5, GREED-6

**작업 내용**
- `backend/main.py`: FastAPI 앱 인스턴스 생성 및 설정
  - `CORSMiddleware` 추가: `allow_origins=["http://localhost:5173"]`
  - `runs`, `analyses` 라우터 등록 (`include_router`)
  - 앱 시작 시 `Base.metadata.create_all(engine)` 호출 (테이블 자동 생성)

**완료 조건**
- `uvicorn backend.main:app --reload` 실행 후 오류 없이 기동
- `curl http://localhost:8000/api/runs` → `200 []` 응답 확인
- `curl -X POST http://localhost:8000/api/runs -H "Content-Type: application/json" -d '{"memo":"test"}'` → `201` 및 `id` 필드 포함 응답 확인
- CORS 헤더 확인: `Origin: http://localhost:5173` 요청에 `Access-Control-Allow-Origin` 응답 포함

---

## Phase 2 — CLI

---

### GREED-8 · [BE] cli.py Click 기반 CLI 진입점 구현

**선행 작업:** GREED-7

**작업 내용**
- `backend/cli.py`: Click 기반 CLI 구현
  - `python cli.py run create [--memo TEXT]` → POST /api/runs, run_id 출력
  - `python cli.py analysis save --run-id INT --ticker STR --name STR --model STR --file PATH` → 파일 내용 읽어 POST /api/analyses
  - `python cli.py analysis save-dir --run-id INT --model STR --dir PATH` → 디렉터리 내 전체 `.md` 파일 일괄 저장
- httpx 사용하여 백엔드 API 호출 (base URL: `http://localhost:8000/api`)
- 저장 성공 시 `[OK] {ticker} {name} — {judgment}`, 실패 시 `[FAIL] {ticker} — 파싱 실패: {failed_fields}` 출력

**완료 조건**
- `python backend/cli.py run create --memo "CLI 테스트"` → run_id 정수 출력 확인
- `python backend/cli.py analysis save --run-id 1 --ticker 005930 --name 삼성전자 --model claude --file sample.md` → `[OK]` 출력 확인
- `python backend/cli.py analysis save-dir --run-id 1 --model claude --dir scripts/pick_output` → 성공/실패 집계 출력 확인

---

## Phase 3 — Frontend

---

### GREED-9 · [FE] Vite + React + TypeScript + Tailwind CSS 프로젝트 초기화

**선행 작업:** GREED-7

**작업 내용**
- `frontend/` 디렉터리에 Vite + React + TypeScript 프로젝트 초기화
- 패키지 설치:
  - `react-router-dom`
  - `axios`
  - `@tanstack/react-query`
  - `react-markdown` + `remark-gfm`
  - `tailwindcss` + `postcss` + `autoprefixer`
- `tailwind.config.js`, `postcss.config.js` 설정
- `vite.config.ts` proxy 설정: `/api` → `http://localhost:8000`
- `src/App.tsx`: React Router `BrowserRouter` 및 `QueryClientProvider` 래핑
- 기본 라우트 3개 placeholder 등록 (`/`, `/runs/:runId`, `/analyses/:id`)

**완료 조건**
- `npm run dev` 실행 후 `http://localhost:5173` 접속 시 React 앱 렌더링 확인
- `npm run build` 타입 에러 없이 빌드 성공
- `http://localhost:5173/api/runs` 프록시 → 백엔드 `200` 응답 확인

---

### GREED-10 · [FE] API 클라이언트 및 React Query 훅 구현

**선행 작업:** GREED-9

**작업 내용**
- `src/api/client.ts`: axios 인스턴스 (`baseURL: /api`)
- `src/api/runs.ts`: runs 관련 API 함수
  - `fetchRuns()`, `fetchRun(runId)`, `createRun(memo)`
- `src/api/analyses.ts`: analyses 관련 API 함수
  - `fetchAnalyses(runId, judgment?)`, `fetchAllAnalyses(filters?)`, `fetchAnalysis(id)`, `fetchHistory(id)`, `createAnalysis(payload)`
- `src/hooks/useRuns.ts`: `useQuery` / `useMutation` 훅
- `src/hooks/useAnalyses.ts`: `useQuery` / `useMutation` 훅
- TypeScript 타입 정의 (`src/types/index.ts`): `Run`, `Analysis`, `AnalysisSummary`

**완료 조건**
- `npm run build` 타입 에러 없이 통과
- `fetchRuns()` 호출 시 백엔드 `GET /api/runs` 응답 정상 수신 확인 (브라우저 Network 탭)

---

### GREED-11 · [FE] RunListPage 구현

**선행 작업:** GREED-10

**작업 내용**
- `src/pages/RunListPage.tsx`: 실행 목록 페이지
  - `useRuns` 훅으로 실행 목록 조회
  - 각 항목: `created_at`, `memo`, `analysis_count` 표시
  - 항목 클릭 시 `/runs/:runId` 이동
  - "새 실행 만들기" 버튼 → `createRun` mutation 호출
  - 로딩/에러 상태 처리

**완료 조건**
- 브라우저 `http://localhost:5173` 접속 시 실행 목록 렌더링 확인
- 브라우저 `/runs` 접속 시 실행 목록 렌더링 확인
- "새 실행 만들기" 클릭 → 목록 갱신 확인 (React Query invalidation)
- 항목 클릭 → `/runs/{id}` URL 이동 확인

---

### GREED-12 · [FE] StockListPage 구현

**선행 작업:** GREED-10

**작업 내용**
- `src/pages/StockListPage.tsx`: 종목 목록 페이지 (`/runs/:runId`)
  - URL 파라미터 `runId`로 `GET /api/runs/{runId}/analyses` 조회
  - 판정 필터 탭: 전체 / 매수 / 홀드 / 매도 (`?judgment=` query)
  - 각 항목: `ticker`, `name`, `judgment`, `trend`, `cloud_position`, `ma_alignment` 표시
  - 항목 클릭 시 `/analyses/:id` 이동

**완료 조건**
- 브라우저 `/runs/1` 접속 시 종목 목록 렌더링 확인
- "매수" 탭 클릭 → `?judgment=매수` 요청 및 필터링 결과 표시 확인
- 항목 클릭 → `/analyses/{id}` URL 이동 확인

---

### GREED-13 · [FE] ManualInputModal 컴포넌트 구현

**선행 작업:** GREED-10

**작업 내용**
- `src/components/ManualInputModal.tsx`: 수동 마크다운 입력 모달
  - Step 1: 모델 선택 (`claude` / `gpt` / `gemini`)
  - Step 2: 실행 선택 (기존 Run 목록) 또는 새 실행 생성
  - Step 3: ticker, name 입력 + 마크다운 textarea 붙여넣기
  - 실시간 파싱 미리보기: `ParsedSummaryCard` 컴포넌트로 파싱 결과 표시
  - 저장 버튼 → `createAnalysis` mutation 호출
- `src/components/ParsedSummaryCard.tsx`: 파싱된 필드(judgment, trend 등) 카드 표시
- `src/components/MarkdownRenderer.tsx`: `react-markdown` + `remark-gfm` 래퍼

**완료 조건**
- RunListPage 또는 StockListPage에서 "수동 입력" 버튼 클릭 시 모달 오픈 확인
- 마크다운 붙여넣기 → 실시간 `ParsedSummaryCard` 갱신 확인 (프론트엔드 정규식 파싱)
- 저장 클릭 → `POST /api/analyses` 요청 후 모달 닫힘 및 목록 갱신 확인
- 파싱 실패 시 오류 필드 하이라이트 표시 확인

---

### GREED-14 · [FE] AnalysisDetailPage 구현

**선행 작업:** GREED-11, GREED-12, GREED-13

**작업 내용**
- `src/pages/AnalysisDetailPage.tsx`: 분석 상세 페이지 (`/analyses/:id`)
  - `GET /api/analyses/{id}` → `MarkdownRenderer`로 마크다운 렌더링
  - `ParsedSummaryCard`로 파싱 요약 (judgment, trend, cloud_position, ma_alignment, 가격 정보) 표시
  - 우측 사이드바: `GET /api/analyses/{id}/history` → 동일 ticker 이력 목록 표시
  - 이력 항목 클릭 시 해당 분석으로 이동

**완료 조건**
- 브라우저 `/analyses/1` 접속 시 마크다운 렌더링 확인
- `ParsedSummaryCard` 정상 표시 확인 (judgment 배지 색상 구분: 매수=green, 홀드=yellow, 매도=red)
- 사이드바 이력 목록 렌더링 확인
- 이력 항목 클릭 → URL 변경 및 페이지 내용 갱신 확인

---

## Follow-up Tickets

---

### GREED-15 · [FE] AnalysisListPage 구현

**선행 작업:** GREED-6, GREED-10

**작업 내용**
- `src/pages/AnalysisListPage.tsx`: 전체 분석 목록 페이지 (`/analyses`)
  - `GET /api/analyses`로 전체 분석 최신순 조회
  - 판정 필터 탭: 전체 / 매수 / 홀드 / 매도 (`?judgment=` query)
  - 실행 ID 필터 입력 또는 선택 (`?run_id=` query)
  - 각 항목: `created_at`, `ticker`, `name`, `judgment`, `model`, `run_id` 표시
  - 항목 클릭 시 `/analyses/:id` 이동
- `src/App.tsx`
  - `/analyses`를 placeholder가 아닌 `AnalysisListPage`로 연결
  - `/runs`를 placeholder가 아닌 `RunListPage`로 연결

**완료 조건**
- 브라우저 `/analyses` 접속 시 전체 분석 목록 렌더링 확인
- "매수" 탭 클릭 → `?judgment=매수` 요청 및 필터링 결과 표시 확인
- 실행 ID 필터 적용 → `?run_id={id}` 요청 및 해당 실행 분석만 표시 확인
- 항목 클릭 → `/analyses/{id}` URL 이동 확인
