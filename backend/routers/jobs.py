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
  trading_value        일별 거래대금(close*volume)의 주간 합계
  volume_ma20          20주 평균 거래량
  volume_ratio_20      현재 거래량 / 20주 평균 거래량
  ma20/ma60/ma120      종가 기준 20/60/120주 이동평균
  ichi_conv  일목 전환선 (9주 고저 중간값)
  ichi_base  일목 기준선 (26주 고저 중간값)
  ichi_lead1 선행스팬A (전환+기준)/2, 26주 앞에 기록
  ichi_lead2 선행스팬B 52주 고저 중간값, 26주 앞에 기록
  ichi_lag   후행스팬, 현재 종가를 26주 앞 행에 기록
  cloud_top/cloud_bottom     max/min(ichi_lead1, ichi_lead2)
  cloud_thickness            cloud_top - cloud_bottom
  cloud_thickness_pct        현재 종가 대비 구름 두께 비율
  close_vs_cloud_top_pct     구름 상단 대비 종가 위치 비율
  conv_base_gap_pct          현재 종가 대비 전환선-기준선 간격 비율

일목구름 해석:
  구름 위: 가격 > max(lead1, lead2) → 상승 지지 구조
  구름 안: min < 가격 < max → 방향성 불확실
  구름 아래: 가격 < min(lead1, lead2) → 하락 압력 구조
  구름 두께: cloud_thickness가 클수록 지지/저항 강함
  미래 구름: open/high/low/close 가 비어 있는 마지막 26행은
             선행스팬 전용 행. 향후 구름 방향 판단용.
             현재 가격 분석에는 사용하지 않으며, 두께 판단에는 cloud_thickness를 사용.

이동평균 배열:
  정배열: ma20 > ma60 > ma120 → 중장기 상승 추세
  역배열: ma20 < ma60 < ma120 → 중장기 하락 추세
  이격도: (종가 / ma20 - 1) × 100

NaN 처리: NaN 구간 지표는 판단에서 제외하고 명시.

출력 형식 — 반드시 이 구조와 행 이름을 유지:
- 아래 마크다운만 출력하고, 앞뒤 설명/코드블록/요약 문장을 추가하지 마세요.
- 대괄호([]), 슬래시(/), 자리표시자 문구를 그대로 출력하지 마세요.
- 선택형 값은 허용값 중 정확히 하나만 출력하세요.
- `추세`, `구름대 위치`, `MA 배열` 행과 `매매 판정` 제목 아래 단독 볼드 판정 줄을 반드시 포함하세요.
- 가격은 가능하면 실제 숫자와 원 단위로 쓰고, 불가피하게 산정할 수 없을 때만 `없음`을 쓰세요.
- 지지/저항은 가격 순서가 맞아야 합니다: 1차 지지 >= 2차 지지, 2차 저항 >= 1차 저항.
- 매수/홀드 판정에서는 눌림 진입과 돌파 진입을 모두 검토하고, 둘 중 하나가 부적절하면 해당 가격대만 `없음`으로 쓰세요.
- 매수/홀드 판정의 1차 목표는 유효한 진입 가격 중 가장 높은 가격 이상이어야 하고, 손절 기준은 유효한 진입 가격 중 가장 낮은 가격 이하여야 합니다.
- 아래 템플릿의 설명 문구는 출력하지 말고 CSV 분석 결과로 모두 교체하세요.

허용값:
- 추세: 상승, 하락, 횡보
- 구름대 위치: 구름 위, 구름 안, 구름 아래
- MA 배열: 정배열, 역배열, 혼조
- 후행스팬: 가격선 위, 가격선 아래, 교차 중
- 구름 방향: 상승운, 하락운, 전환 예정
- 매매 판정: 매수, 홀드, 매도

## 종목 분석 결과

### 1. 현재 구조 요약
- 추세: 허용값 중 하나
- 구름대 위치: 허용값 중 하나
- MA 배열: 허용값 중 하나
- 후행스팬: 허용값 중 하나

### 2. 핵심 지지/저항선
- 1차 지지: 실제 가격 또는 없음  근거: 지표명과 실제 수치
- 2차 지지: 실제 가격 또는 없음  근거: 지표명과 실제 수치
- 1차 저항: 실제 가격 또는 없음  근거: 지표명과 실제 수치
- 2차 저항: 실제 가격 또는 없음  근거: 지표명과 실제 수치

### 3. 향후 구름 전망 (미래 26주)
- 구름 방향: 허용값 중 하나
- 비고: 실제 구름 두께 변화와 특이사항

### 4. 매매 판정
**허용값 중 하나**
근거:
1. CSV에서 확인한 가장 중요한 수치 근거
2. CSV에서 확인한 두 번째 수치 근거
3. CSV에서 확인한 세 번째 수치 근거
주의사항:
- 실제 리스크 또는 무효화 조건

### 5. 진입/청산 시나리오
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 눌림 진입 | 지지선 부근 조정 매수 조건 | 실제 가격 또는 없음 |
| 돌파 진입 | 저항선/구름 상단 돌파 확인 조건 | 실제 가격 또는 없음 |
| 1차 목표 | 실제 조건 | 실제 가격 또는 없음 |
| 손절 기준 | 실제 조건 | 실제 가격 또는 없음 |

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
    candidates = [
        Path.home() / ".local" / "bin" / "claude.exe",
        Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe",
    ]
    for exe in candidates:
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
    # Pass prompt via stdin; -p "" triggers non-interactive (headless) mode
    cmd = (
        ["gemini.cmd", "-p", "", "--output-format", "text"]
        if sys.platform == "win32"
        else ["gemini", "-p", "", "--output-format", "text"]
    )
    result = subprocess.run(
        cmd,
        capture_output=True,
        input=prompt,
        text=True,
        timeout=CLAUDE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout)[:300])
    lines = result.stdout.splitlines()
    filtered = [ln for ln in lines if not re.match(r'^Active code page:\s*\d+$', ln.strip())]
    return "\n".join(filtered).strip()
