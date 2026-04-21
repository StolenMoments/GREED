# greed — 주봉 기술적 분석 관리 시스템 개발 명세서

> **스택**: FastAPI · SQLite · React · Tailwind CSS  
> **배포 형태**: 로컬 단일 머신 (localhost)  
> **버전**: v1.0 초안

---

## 1. 프로젝트 개요

AI 모델(Claude / GPT / Gemini)이 생성한 주봉 기술적 분석 마크다운 결과물을 저장·파싱·조회하는 로컬 관리 시스템.

**전체 실행 흐름**:

```
[1] scripts/gogo2.py 실행
      └─ KOSPI/KOSDAQ 전종목 스크리닝
      └─ 조건 충족 종목 → pick.py run_pick() 자동 호출
           └─ scripts/pick_output/{ticker}_{name}_weekly_{date}.csv 생성

[2] AI 에이전트 SKILL 실행 (Claude Code / Codex CLI / Gemini CLI)
      └─ pick_output/*.csv 순회
      └─ 각 CSV + 시스템 프롬프트 → AI 분석 → 마크다운 생성
      └─ greed 백엔드 API POST → DB 저장

[3] Web UI 조회
      └─ 실행 목록(/runs) 또는 분석 목록(/analyses)
          ├─ 실행 목록 → 종목 목록(/runs/:runId) → 분석 상세(/analyses/:id)
          └─ 분석 목록 → 분석 상세(/analyses/:id)
```

---

## 2. 디렉터리 구조

```
greed/
├── scripts/                        # 스크리닝 스크립트
│   ├── gogo2.py                    # 전종목 스크리닝 (KOSPI/KOSDAQ)
│   ├── pick.py                     # 개별 종목 5년치 주봉 CSV 추출
│   ├── pick_output/                # pick.py 출력 디렉터리
│   │   └── {ticker}_{name}_weekly_{YYYYMMDD}.csv
│   └── screening_YYYYMMDD.csv      # gogo2 스크리닝 결과 (종목 목록)
│
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── crud.py
│   ├── parser.py                   # 마크다운 파싱 전담 모듈
│   ├── routers/
│   │   ├── runs.py
│   │   └── analyses.py
│   └── cli.py                      # Click 기반 CLI 진입점
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── RunListPage.tsx
│   │   │   ├── AnalysisListPage.tsx
│   │   │   ├── StockListPage.tsx
│   │   │   └── AnalysisDetailPage.tsx
│   │   ├── components/
│   │   │   ├── ManualInputModal.tsx
│   │   │   ├── ParsedSummaryCard.tsx
│   │   │   └── MarkdownRenderer.tsx
│   │   ├── api/
│   │   └── App.tsx
│   └── package.json
│
├── greed.db                        # SQLite DB
└── README.md
```

---

## 3. scripts/ — 스크리닝 파이프라인

### 3-1. gogo2.py

KOSPI·KOSDAQ 전종목을 멀티스레드로 순회하며 아래 조건을 충족하는 종목을 추린다.

| 조건 | 내용 |
|------|------|
| ① 캔들 구름 돌파 | 최근 `candle_max_lookback`(기본 3)주 이내 캔들이 일목 구름 상단 돌파 |
| ② 돌파 시 거래량 | 직전 4주 평균 대비 `vol_multiplier`(기본 1.5)배 이상 |
| ③ MA 또는 GC | MA20/60/120 중 하나 이상이 구름 돌파 OR 골든크로스 발생 |
| 이격도 필터 | 종가 ≤ 구름 상단 × 1.25 |
| 시총 필터 | 50B KRW 이상 |
| 종목 제외 | 우선주(코드 끝 0 아님), 스팩, 리츠 |

**출력**: `scripts/screening_YYYYMMDD.csv`  
**파라미터**: KOSPI 12/6/6 / KOSDAQ 8/4/4 (candle/ma/gc lookback, CLI 오버라이드 가능)  
**완료 후**: 조건 충족 종목 각각에 대해 `pick.run_pick()` 자동 호출

### 3-2. pick.py

gogo2.py 완료 후 자동으로 각 종목의 5년치 주봉 데이터를 추출한다.

**출력 파일명**:
```
scripts/pick_output/{ticker}_{name}_weekly_{YYYYMMDD}.csv
예: 005930_삼성전자_weekly_20250420.csv
```

**CSV 컬럼**: `ticker`, `name`, `open`, `high`, `low`, `close`, `volume`, `ma20`, `ma60`, `ma120`, `ichi_conv`, `ichi_base`, `ichi_lead1`, `ichi_lead2`, `ichi_lag`

**행 구성**: 실제 가격 행(약 260주) + 선행스팬 전용 미래 26행 (open/high/low/close = NaN)

---

## 4. skills/ — AI 에이전트 분석 SKILL

### 4-1. SKILL 역할

에이전트(Claude Code / Codex CLI / Gemini CLI)가 `scripts/pick_output/` 디렉터리의 CSV를
읽어 분석 마크다운을 생성하고, greed 백엔드 API에 저장하는 전체 흐름을 지시한다.

에이전트 자신이 분석 AI로서 동작하므로 외부 API 호출이 필요 없다.
에이전트가 시스템 프롬프트 지침에 따라 CSV를 직접 분석하고 마크다운을 생성한다.

### 4-2. `skills/weekly-analysis/SKILL.md` 내용 명세

아래가 실제 파일에 작성할 내용이다.

---

```markdown
# weekly-analysis

## 역할
주봉 기술적 분석 스킬. scripts/pick_output/ 의 CSV를 읽어
시스템 프롬프트에 따라 분석하고 greed 백엔드에 저장한다.

## 사전 조건 확인
1. greed 백엔드 서버 응답 확인: GET http://localhost:8000/api/runs
   - 응답 없으면 중단하고 사용자에게 서버 시작을 요청한다
2. scripts/pick_output/ 디렉터리 및 CSV 파일 존재 확인
   - 비어 있으면 사용자에게 먼저 `python scripts/gogo2.py` 실행 여부를 확인한다

## 실행 절차

### Step 1 — 새 Run 생성
POST http://localhost:8000/api/runs
Body: { "memo": "YYYYMMDD 자동 분석 — {에이전트명}" }
응답에서 run_id 저장.

### Step 2 — CSV 파일 목록 수집
scripts/pick_output/*.csv 파일 목록을 수집한다.
파일명 패턴: {ticker}_{name}_weekly_{YYYYMMDD}.csv
  - ticker: 첫 번째 _ 이전 6자리
  - name: ticker 이후 ~ _weekly_ 이전 문자열

### Step 3 — 각 종목 분석 (파일마다 반복)

CSV 전체 내용을 읽어 아래 [분석 지침]에 따라 마크다운을 생성한다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[분석 지침 — SYSTEM]

당신은 한국 주식시장 전문 기술적 분석가입니다.
주봉(Weekly) OHLCV 데이터와 기술적 지표를 기반으로 분석하며,
반드시 아래 규칙을 따릅니다.

컬럼 정의:
  date       주봉 시작일 (월요일 기준)
  open/high/low/close  주간 시가/고가/저가/종가
  volume     주간 누적 거래량
  ma20/ma60/ma120      종가 기준 20/60/120주 이동평균
  ichi_conv  일목 전환선 (9주 고저 중간값)
  ichi_base  일목 기준선 (26주 고저 중간값)
  ichi_lead1 선행스팬A (전환+기준)/2, 26주 앞에 기록
  ichi_lead2 선행스팬B 52주 고저 중간값, 26주 앞에 기록
  ichi_lag   후행스팬, 현재 종가를 26주 앞 행에 기록

일목구름 해석:
  구름 위: 가격 > max(lead1, lead2) → 상승 지지 구조
  구름 안: min < 가격 < max → 방향성 불확실
  구름 아래: 가격 < min(lead1, lead2) → 하락 압력 구조
  구름 두께: |lead1 - lead2| 클수록 지지/저항 강함
  미래 구름: open/high/low/close 가 비어 있는 마지막 26행은
             선행스팬 전용 행. 향후 구름 방향 판단용.
             현재 가격 분석에는 사용하지 않음.

이동평균 배열:
  정배열: ma20 > ma60 > ma120 → 중장기 상승 추세
  역배열: ma20 < ma60 < ma120 → 중장기 하락 추세
  이격도: (종가 / ma20 - 1) × 100

NaN 처리: NaN 구간 지표는 판단에서 제외하고 명시.

출력 형식 — 반드시 이 구조를 유지:

## 종목 분석 결과

### 1. 현재 구조 요약
- 추세: [상승 / 하락 / 횡보]
- 구름대 위치: [구름 위 / 구름 안 / 구름 아래]
- MA 배열: [정배열 / 역배열 / 혼조]
- 후행스팬: [가격선 위 / 가격선 아래 / 교차 중]

### 2. 핵심 지지/저항선
- 1차 지지: [가격]  근거: [지표명]
- 2차 지지: [가격]  근거: [지표명]
- 1차 저항: [가격]  근거: [지표명]
- 2차 저항: [가격]  근거: [지표명]

### 3. 향후 구름 전망 (미래 26주)
- 구름 방향: [상승운 / 하락운 / 전환 예정]
- 비고: [구름 두께 변화 등 특이사항]

### 4. 매매 판정
**[매수 / 홀드 / 매도]**
근거:
1. [가장 중요한 근거]
2. [두 번째 근거]
3. [세 번째 근거]
주의사항:
- [리스크 또는 무효화 조건]

### 5. 진입/청산 시나리오
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 진입 조건 | [조건 서술] | [가격] |
| 1차 목표 | [조건 서술] | [가격] |
| 손절 기준 | [조건 서술] | [가격] |

수치 근거 없는 추상적 표현 사용 금지.
기술적 분석 외 펀더멘털, 뉴스, 경제 이슈 언급 금지.

[USER]
CSV는 5년치 주봉 데이터입니다. 마지막 26행은 선행스팬 전용 미래 구름 행입니다.
기술적 분석을 수행하고 매수/홀드/매도 판정을 내려주세요.

{csv_content 여기에 삽입}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### Step 4 — 결과 저장
분석 마크다운 생성 후 greed 백엔드 API에 저장:

POST http://localhost:8000/api/analyses
Content-Type: application/json
{
  "run_id": <step1 run_id>,
  "ticker": "<파일명 추출>",
  "name": "<파일명 추출>",
  "model": "<claude | gpt | gemini>",
  "markdown": "<생성된 마크다운 전문>"
}

응답 처리:
  201 → [OK] {ticker} {name} — {judgment}
  422 → [FAIL] {ticker} — 파싱 실패: {failed_fields} (건너뜀)

### Step 5 — 완료 보고
성공: N개 / 실패: M개 / Run ID: {run_id}

## 컨텍스트 용량 기준
| 모델 컨텍스트 | 권장 행 수 |
|-------------|-----------|
| 200k+ (Claude) | 전체 (~286행) |
| 128k (GPT-4o) | 최근 200행 + 미래 26행 |
| 32k 이하 | 최근 100행 + 미래 26행 |
미래 26행은 항상 포함 (구름 전망 분석에 필수).

## 에이전트별 호출
- Claude Code : /weekly-analysis
- Codex CLI   : /prompts:weekly-analysis
- Gemini CLI  : /weekly-analysis
```

---

### 4-3. 에이전트별 설치 경로

| 에이전트 | SKILL 배포 경로 |
|----------|----------------|
| Claude Code (프로젝트) | `greed/.claude/skills/weekly-analysis/SKILL.md` |
| Claude Code (글로벌) | `~/.claude/skills/weekly-analysis/SKILL.md` |
| Codex CLI (글로벌) | `~/.codex/skills/weekly-analysis/SKILL.md` |
| Gemini CLI (글로벌) | `~/.gemini/skills/weekly-analysis/SKILL.md` |

### 4-4. `skills/install.sh`

원본은 Codex CLI 글로벌 경로에 두고, 나머지는 심볼릭 링크로 연결한다.
SKILL.md를 수정하면 모든 에이전트에 즉시 반영된다.

```bash
#!/bin/bash
# greed SKILL 배포 스크립트
# 원본: ~/.codex/skills/weekly-analysis/SKILL.md
# 나머지: 모두 위 원본을 가리키는 symlink
set -e

SKILL_SRC="$(cd "$(dirname "$0")/weekly-analysis" && pwd)/SKILL.md"

# ── 1. Codex CLI 글로벌에 원본 배치
CODEX_DEST="$HOME/.codex/skills/weekly-analysis"
mkdir -p "$CODEX_DEST"
cp "$SKILL_SRC" "$CODEX_DEST/SKILL.md"
echo "[OK] 원본 → $CODEX_DEST/SKILL.md"

# ── 2. 나머지 에이전트는 원본을 가리키는 symlink 생성
SYMLINK_TARGETS=(
  "$HOME/.claude/skills/weekly-analysis/SKILL.md"
  "$HOME/.gemini/skills/weekly-analysis/SKILL.md"
  "$(pwd)/.claude/skills/weekly-analysis/SKILL.md"   # Claude Code 프로젝트 레벨
)

for TARGET in "${SYMLINK_TARGETS[@]}"; do
  mkdir -p "$(dirname "$TARGET")"
  ln -sf "$CODEX_DEST/SKILL.md" "$TARGET"
  echo "[OK] symlink → $TARGET"
done

echo ""
echo "설치 완료. SKILL 수정 시 $CODEX_DEST/SKILL.md 만 편집하면 됩니다."
```

### `skills/install.bat` (Windows CMD)

> `mklink` 는 관리자 권한이 필요하다. CMD를 **관리자 권한으로 실행**하거나,
> Windows 설정 → 개발자 모드를 활성화하면 일반 권한에서도 동작한다.

```bat
@echo off
setlocal

:: ── 원본 경로 (Codex CLI 글로벌)
set CODEX_DEST=%USERPROFILE%\.codex\skills\weekly-analysis
set SKILL_ORIG=%CODEX_DEST%\SKILL.md

:: ── 스크립트 위치 기준으로 소스 경로 계산
set SCRIPT_DIR=%~dp0
set SKILL_SRC=%SCRIPT_DIR%weekly-analysis\SKILL.md

:: ── 1. Codex CLI 글로벌에 원본 배치
if not exist "%CODEX_DEST%" mkdir "%CODEX_DEST%"
copy /Y "%SKILL_SRC%" "%SKILL_ORIG%" >nul
echo [OK] 원본 -^> %SKILL_ORIG%

:: ── 2. symlink 생성 함수 (mklink /H = 하드링크, 관리자 불필요 대안)
::     심볼릭링크(mklink) 실패 시 하드링크(mklink /H)로 폴백
call :make_link "%USERPROFILE%\.claude\skills\weekly-analysis\SKILL.md"
call :make_link "%USERPROFILE%\.gemini\skills\weekly-analysis\SKILL.md"

:: ── 3. Claude Code 프로젝트 레벨 (.claude는 스크립트 위치 기준 두 단계 위)
for %%I in ("%SCRIPT_DIR%..") do set PROJECT_ROOT=%%~fI
call :make_link "%PROJECT_ROOT%\.claude\skills\weekly-analysis\SKILL.md"

echo.
echo 설치 완료. SKILL 수정 시 아래 파일만 편집하면 됩니다.
echo %SKILL_ORIG%
goto :eof

:: ── 심볼릭링크 생성 서브루틴
:make_link
set TARGET=%~1
set TARGET_DIR=%~dp1
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"
if exist "%TARGET%" del /F /Q "%TARGET%"
mklink "%TARGET%" "%SKILL_ORIG%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] symlink -^> %TARGET%
) else (
    mklink /H "%TARGET%" "%SKILL_ORIG%" >nul 2>&1
    if %errorlevel% equ 0 (
        echo [OK] hardlink -^> %TARGET%
    ) else (
        echo [WARN] 링크 생성 실패, 파일 복사로 대체: %TARGET%
        copy /Y "%SKILL_ORIG%" "%TARGET%" >nul
    )
)
goto :eof
```

---

## 5. 데이터베이스 스키마

### 5-1. `runs` 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INTEGER PK AUTOINCREMENT | 실행 식별자 |
| `memo` | TEXT NULLABLE | 사용자 메모 |
| `created_at` | DATETIME DEFAULT NOW | 생성 시각 |

### 5-2. `analyses` 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `run_id` | INTEGER FK → runs.id | 소속 실행 |
| `ticker` | TEXT NOT NULL | 종목 코드 |
| `name` | TEXT NOT NULL | 종목명 |
| `model` | TEXT NOT NULL | `claude` \| `gpt` \| `gemini` |
| `markdown` | TEXT NOT NULL | 원본 마크다운 전문 |
| `judgment` | TEXT NOT NULL | `매수` \| `홀드` \| `매도` |
| `trend` | TEXT NOT NULL | `상승` \| `하락` \| `횡보` |
| `cloud_position` | TEXT NOT NULL | `구름 위` \| `구름 안` \| `구름 아래` |
| `ma_alignment` | TEXT NOT NULL | `정배열` \| `역배열` \| `혼조` |
| `entry_price` | REAL NULLABLE | 진입 가격 |
| `target_price` | REAL NULLABLE | 1차 목표가 |
| `stop_loss` | REAL NULLABLE | 손절 기준가 |
| `created_at` | DATETIME DEFAULT NOW | |

**인덱스**: `(run_id)`, `(ticker)`, `(judgment)`

---

## 6. 마크다운 파싱 명세 (`parser.py`)

### 6-1. 파싱 대상 및 정규식

| 필드 | 정규식 패턴 (Python raw string) |
|------|-------------------------------|
| `judgment` | `\*\*(매수\|홀드\|매도)\*\*` |
| `trend` | `추세:\s*(상승\|하락\|횡보)` |
| `cloud_position` | `구름대 위치:\s*(구름 위\|구름 안\|구름 아래)` |
| `ma_alignment` | `MA 배열:\s*(정배열\|역배열\|혼조)` |
| `entry_price` | `진입 조건.+?\|\s*([\d,]+)` |
| `target_price` | `1차 목표.+?\|\s*([\d,]+)` |
| `stop_loss` | `손절 기준.+?\|\s*([\d,]+)` |
| `ticker` | `종목\s*코드[:\s]+([A-Z0-9]{5,6})` |
| `name` | `종목\s*명[:\s]+(.+?)(\n\|$)` |

> 가격 파싱: 쉼표 제거 후 `float()`. 범위 표기는 하한값 사용.

### 6-2. 파싱 실패 처리

```python
@dataclass
class ParseResult:
    data: dict
    failed: list[str]
    success: bool       # 필수 필드 전부 성공 여부

# 필수: judgment, trend, cloud_position, ma_alignment
# 선택 (NULL 허용): entry_price, target_price, stop_loss
# ticker, name: SKILL 경로 → 파일명 추출 / 웹 UI → 마크다운 파싱
```

---

## 7. API 엔드포인트 명세

Base URL: `http://localhost:8000/api`

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/runs` | 새 실행 생성 |
| `GET` | `/runs` | 실행 목록 (종목 수 포함) |
| `GET` | `/runs/{run_id}` | 실행 상세 |
| `POST` | `/analyses` | 분석 저장 (파싱 포함) |
| `GET` | `/analyses` | 전체 분석 목록 최신순 (`?judgment=매수&run_id=1`) |
| `GET` | `/runs/{run_id}/analyses` | 종목 목록 (`?judgment=매수`) |
| `GET` | `/analyses/{id}` | 분석 상세 |
| `GET` | `/analyses/{id}/history` | 동일 ticker 이력 |

**POST /analyses** 실패 응답 `422`:
```json
{ "detail": "파싱 실패", "failed_fields": ["judgment"] }
```

---

## 8. CLI 명세 (`cli.py`)

```bash
python cli.py run create [--memo TEXT]
python cli.py analysis save --run-id INT --ticker STR --name STR --model STR --file PATH
python cli.py analysis save-dir --run-id INT --model STR --dir PATH
```

---

## 9. 프론트엔드 페이지 명세

| Path | 페이지 |
|------|--------|
| `/` | `/runs`로 리다이렉트 |
| `/runs` | RunListPage — 실행 목록 |
| `/analyses` | AnalysisListPage — 전체 분석 목록 + 판정/실행 필터 |
| `/runs/:runId` | StockListPage — 종목 목록 + 판정 필터 |
| `/analyses/:id` | AnalysisDetailPage — 상세 + 이력 사이드바 |

**ManualInputModal**: 모델 선택 → 실행 선택/생성 → 마크다운 붙여넣기 → 실시간 파싱 미리보기 → 저장

---

## 10. 기술 스택

| 영역 | 패키지 |
|------|--------|
| Backend | `fastapi` · `uvicorn` · `sqlalchemy` · `pydantic v2` · `click` · `httpx` |
| Frontend | `react` + `typescript` · `react-router-dom` · `axios` · `react-markdown` + `remark-gfm` · `tailwindcss` · `@tanstack/react-query` |
| Scripts | `FinanceDataReader` · `pandas` · `numpy` · `concurrent.futures` |

---

## 11. 개발 순서

```
Phase 0 — SKILL 배포
  ① skills/weekly-analysis/SKILL.md 작성 (§4-2 내용)
  ② bash skills/install.sh

Phase 1 — Backend Core
  ③ database.py + models.py
  ④ parser.py + 단위 테스트 통과
  ⑤ routers/runs.py + routers/analyses.py
  ⑥ main.py (CORS: localhost:5173)

Phase 2 — CLI
  ⑦ cli.py

Phase 3 — Frontend (Impeccable SKILL 적용)
  ⑧ Vite + React + Tailwind 초기화
  ⑨ RunListPage + AnalysisListPage + StockListPage
  ⑩ ManualInputModal
  ⑪ AnalysisDetailPage
```

---

## 12. 파싱 엣지케이스

| 상황 | 처리 |
|------|------|
| 가격 범위 표기 (`53,000 ~ 55,000`) | 하한값 사용 |
| 가격에 단위 포함 (`75,000원`) | 숫자만 추출 |
| 볼드 없는 판정 (`매수`) | fallback 패턴 추가 시도 |
| `N/A`, `-`, `미정` | `NULL` 저장 (선택 필드) |
| ticker/name 미포함 | 웹 UI: 422 / SKILL: 파일명에서 추출 |
