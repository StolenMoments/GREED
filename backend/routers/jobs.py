from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.crud import (
    create_analysis,
    create_job,
    get_job,
    get_jobs,
    get_run,
    update_job_done,
    update_job_failed,
)
from backend.database import SessionLocal, get_db
from backend.parser import parse_markdown
from backend.schemas import AnalysisCreate, JobRead, JobTriggerRequest


SYSTEM_PROMPT = """당신은 한국 주식시장 전문 기술적 분석가입니다.
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

CSV는 5년치 주봉 데이터입니다. 마지막 26행은 선행스팬 전용 미래 구름 행입니다.
기술적 분석을 수행하고 매수/홀드/매도 판정을 내려주세요."""

CLAUDE_TIMEOUT_SECONDS = 300
PICK_OUTPUT_DIR = Path("pick_output")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/trigger-analysis", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def trigger_analysis_endpoint(
    payload: JobTriggerRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobRead:
    if get_run(db, payload.run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    ticker = payload.ticker.strip().zfill(6)
    job = create_job(db, ticker=ticker, run_id=payload.run_id, model=payload.model)
    background_tasks.add_task(run_analysis_pipeline, job.id)
    return job


@router.get("", response_model=list[JobRead])
def list_jobs_endpoint(run_id: int | None = None, db: Session = Depends(get_db)) -> list[JobRead]:
    if run_id is not None and get_run(db, run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return get_jobs(db, run_id=run_id)


@router.get("/{job_id}", response_model=JobRead)
def get_job_endpoint(job_id: int, db: Session = Depends(get_db)) -> JobRead:
    job = get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def run_analysis_pipeline(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = get_job(db, job_id)
        if job is None:
            return

        ticker = job.ticker.strip().zfill(6)
        job_output_dir = PICK_OUTPUT_DIR / "jobs" / str(job.id)
        try:
            stock_name = _resolve_stock_name(ticker)
            _run_pick(ticker, stock_name, job_output_dir)
        except Exception as exc:
            update_job_failed(db, job, f"pick: {exc}")
            return

        csv_path = _latest_csv_path(ticker, job_output_dir)
        if csv_path is None:
            update_job_failed(db, job, "pick: CSV 파일 생성 안 됨")
            return

        try:
            csv_text = csv_path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            update_job_failed(db, job, f"pick: {exc}")
            return
        selected_model = job.model or "claude"
        if selected_model == "codex":
            runner, analysis_model = _run_codex, "codex-cli"
        elif selected_model == "gemini":
            runner, analysis_model = _run_gemini, "gemini-cli"
        else:
            runner, analysis_model = _run_claude, "claude-code"

        try:
            raw = runner(csv_text)
        except subprocess.TimeoutExpired:
            update_job_failed(db, job, f"{selected_model}: 180s 타임아웃 초과")
            return
        except RuntimeError as exc:
            update_job_failed(db, job, f"{selected_model}: {str(exc)[:300]}")
            return
        except Exception as exc:
            update_job_failed(db, job, f"{selected_model}: {exc}")
            return

        if not raw:
            update_job_failed(db, job, f"{selected_model}: 빈 응답 반환")
            return

        parse_result = parse_markdown(raw)
        if not parse_result.success:
            failed_str = ", ".join(parse_result.failed)
            update_job_failed(db, job, f"parser: [{failed_str}] 필드 누락. 원본 앞 300자: {raw[:300]}", raw_markdown=raw)
            return

        try:
            analysis = create_analysis(
                db,
                AnalysisCreate(
                    run_id=job.run_id,
                    ticker=ticker,
                    name=stock_name or ticker,
                    model=analysis_model,
                    markdown=raw,
                    **parse_result.data,
                ),
            )
            update_job_done(db, job, analysis.id, raw_markdown=raw)
        except Exception as exc:
            db.rollback()
            update_job_failed(db, job, f"db: {exc}")
    finally:
        db.close()


def _run_pick(ticker: str, stock_name: str, output_dir: Path) -> None:
    from scripts.pick import run_pick

    run_pick(ticker, years=5, output_dir=str(output_dir), stock_name=stock_name)


def _resolve_stock_name(ticker: str) -> str:
    from scripts.pick import resolve_stock_name

    return resolve_stock_name(ticker)


def _latest_csv_path(ticker: str, output_dir: Path) -> Path | None:
    files = sorted(output_dir.glob(f"{ticker}_*.csv"), key=lambda path: path.stat().st_mtime)
    if not files:
        return None
    return files[-1]


def _trim_csv(csv_text: str, max_data_rows: int) -> str:
    lines = csv_text.strip().splitlines()
    header, data_rows = lines[0], lines[1:]
    future_rows, hist_rows = data_rows[-26:], data_rows[:-26]
    trimmed = hist_rows[-max_data_rows:] if len(hist_rows) > max_data_rows else hist_rows
    return "\n".join([header] + trimmed + future_rows)


def _claude_cmd() -> list[str]:
    if sys.platform != "win32":
        return ["claude", "-p"]
    # claude.cmd (batch wrapper) doesn't propagate claude.exe exit codes,
    # so batch artifacts ("Active code page", "Terminate batch job") leak into stdout.
    # Call claude.exe directly when available.
    npm_root = Path.home() / "AppData" / "Roaming" / "npm" / "node_modules"
    exe = npm_root / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    if exe.exists():
        return [str(exe), "-p"]
    return ["claude.cmd", "-p"]


def _run_claude(csv_text: str) -> str:
    prompt = f"{SYSTEM_PROMPT}\n\n{csv_text}"
    result = subprocess.run(
        _claude_cmd(),
        capture_output=True,
        input=prompt,
        text=True,
        timeout=CLAUDE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout)[:300])
    return result.stdout.strip()


def _parse_codex_output(output: str) -> str:
    # Strip Windows chcp artifact ("Active code page: NNN") that leaks into stdout
    lines = output.splitlines()
    filtered = [ln for ln in lines if not re.match(r'^Active code page:\s*\d+$', ln.strip())]
    candidate = "\n".join(filtered).strip()
    # If output wrapped in conversation format (user/codex/tokens sections), extract response only
    conv_match = re.search(r'\ncodex\n(.+?)(?:\ntokens used\b|$)', candidate, re.DOTALL)
    if conv_match:
        return conv_match.group(1).strip()
    return candidate


def _run_codex(csv_text: str) -> str:
    prompt = f"{SYSTEM_PROMPT}\n\n{_trim_csv(csv_text, 200)}"
    cmd = ["codex.cmd", "exec", "-"] if sys.platform == "win32" else ["codex", "exec", "-"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        input=prompt,
        text=True,
        timeout=CLAUDE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout)[:300])
    return _parse_codex_output(result.stdout)


def _run_gemini(csv_text: str) -> str:
    prompt = f"{SYSTEM_PROMPT}\n\n{csv_text}"
    cmd = ["gemini"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        input=prompt,
        text=True,
        timeout=CLAUDE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:300])
    return result.stdout.strip()
