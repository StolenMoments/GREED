from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
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
from backend.models import AnalysisJob
from backend.parser import parse_markdown
from backend.schemas import AnalysisCreate, JobRead, JobTriggerRequest
from backend.tickers import market_for_ticker, normalize_ticker, is_korean_text
from backend.timezone import seoul_now


KR_SYSTEM_PROMPT = """당신은 한국 주식시장 전문 기술적 분석가입니다.
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
  atr14      14주 Average True Range, 주간 평균 변동폭
  atr14_pct  현재 종가 대비 atr14 비율
  rsi14      14주 RSI, 과열/침체 판단 보조 지표
  macd       EMA12 - EMA26
  macd_signal        MACD의 9주 EMA 신호선
  macd_hist  macd - macd_signal, 모멘텀 강화/약화 판단 보조 지표
  ma20_60_cross      ma20/ma60 교차 신호. golden/dead 값만 판단, 빈 값은 신호 없음
  ma60_120_cross     ma60/ma120 교차 신호. golden/dead 값만 판단, 빈 값은 신호 없음
  macd_signal_cross  macd/macd_signal 교차 신호. bullish/bearish 값만 판단, 빈 값은 신호 없음
  rsi_divergence     가격 스윙과 RSI 간 다이버전스. bullish/bearish 값만 판단
  macd_hist_divergence       가격 스윙과 MACD histogram 간 다이버전스. bullish/bearish 값만 판단
  strict_divergence  RSI와 MACD histogram이 같은 방향으로 동시에 확인된 엄격 다이버전스
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

변동성/모멘텀 해석:
  ATR: 손절 폭과 진입 가격대가 현재 변동성 대비 과도하게 좁거나 넓지 않은지 판단
  RSI: 70 이상은 과열, 30 이하는 침체 가능성으로 보되 추세와 함께 해석
  MACD: macd가 macd_signal 위이고 macd_hist가 증가하면 모멘텀 강화, 반대는 약화로 해석
  교차 신호: golden/bullish는 추세 전환 또는 강화 근거, dead/bearish는 매수 보류 또는 리스크 근거
  다이버전스: strict_divergence=bullish는 하락 둔화/반등 가능성 보조 근거로만 사용하고, 구름/MA 구조가 약하면 단독 매수 근거로 쓰지 않음
  다이버전스: strict_divergence=bearish는 상승 둔화/조정 가능성 및 손절 주의 근거로 사용

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

SYSTEM_PROMPT = KR_SYSTEM_PROMPT

US_SYSTEM_PROMPT = KR_SYSTEM_PROMPT.replace(
    "당신은 한국 주식시장 전문 기술적 분석가입니다.",
    "당신은 미국 주식시장 전문 기술적 분석가입니다.",
).replace(
    "date       주봉 시작일 (월요일 기준)",
    "date       주봉 종료일 (금요일 기준)",
).replace(
    "가격은 가능하면 실제 숫자와 원 단위로 쓰고",
    "가격은 가능하면 실제 숫자와 달러 단위로 쓰고",
)

ANALYSIS_RESULT_TIMEOUT_SECONDS = 30 * 60
PICK_OUTPUT_DIR = Path("pick_output")
ANALYSIS_FILENAME = "analysis.md"
PROMPT_FILENAME = "prompt.md"
STDOUT_LOG_FILENAME = "stdout.log"
STDERR_LOG_FILENAME = "stderr.log"
PID_FILENAME = "model.pid"
EXIT_CODE_FILENAME = "exit_code.txt"
MODEL_START_GRACE_SECONDS = 15
LOG_TAIL_CHARS = 1200
_FINALIZE_LOCKS: dict[int, Lock] = {}
_FINALIZE_LOCKS_GUARD = Lock()

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
VALID_JOB_STATUSES = {"pending", "done", "failed"}


@router.post("/trigger-analysis", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def trigger_analysis_endpoint(
    payload: JobTriggerRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobRead:
    if get_run(db, payload.run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    ticker = normalize_ticker(payload.ticker)
    if is_korean_text(payload.ticker):
        from backend.crud import search_krx_stocks
        matches = search_krx_stocks(db, payload.ticker.strip())
        if matches:
            ticker = matches[0].code
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"종목명을 찾을 수 없습니다: {payload.ticker}")
    job = create_job(db, ticker=ticker, run_id=payload.run_id, model=payload.model)
    background_tasks.add_task(run_analysis_pipeline, job.id)
    return job


@router.get("", response_model=list[JobRead])
def list_jobs_endpoint(
    run_id: int | None = None,
    status_filter: list[str] | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[JobRead]:
    if run_id is not None and get_run(db, run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if status_filter:
        invalid_statuses = sorted(set(status_filter) - VALID_JOB_STATUSES)
        if invalid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid job status: {', '.join(invalid_statuses)}",
            )
    finalized_jobs = [
        _finalize_pending_job_if_ready(db, job)
        for job in get_jobs(db, run_id=run_id)
    ]
    if not status_filter:
        return finalized_jobs

    allowed_statuses = set(status_filter)
    return [job for job in finalized_jobs if job.status in allowed_statuses]


@router.get("/{job_id}", response_model=JobRead)
def get_job_endpoint(job_id: int, db: Session = Depends(get_db)) -> JobRead:
    job = get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _finalize_pending_job_if_ready(db, job)


def run_analysis_pipeline(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = get_job(db, job_id)
        if job is None:
            return

        ticker = normalize_ticker(job.ticker)
        job_output_dir = _job_output_dir(job.id)
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

        selected_model = job.model or "claude"
        system_prompt = _system_prompt_for_ticker(ticker)
        runner = _runner_for_model(selected_model)
        analysis_path = _analysis_path(job.id)
        prompt_path = job_output_dir / PROMPT_FILENAME
        stdout_path = job_output_dir / STDOUT_LOG_FILENAME
        stderr_path = job_output_dir / STDERR_LOG_FILENAME
        pid_path = job_output_dir / PID_FILENAME
        exit_code_path = job_output_dir / EXIT_CODE_FILENAME
        try:
            csv_text = csv_path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            update_job_failed(db, job, f"pick: {exc}")
            return

        try:
            _start_runner(
                runner,
                csv_text,
                system_prompt,
                analysis_path,
                prompt_path,
                stdout_path,
                stderr_path,
                pid_path,
                exit_code_path,
            )
        except Exception as exc:
            update_job_failed(db, job, f"model_start: {selected_model}: {str(exc)[:300]}")
    finally:
        db.close()


def _finalize_pending_job_if_ready(db: Session, job: AnalysisJob) -> AnalysisJob:
    if job.status != "pending":
        return job

    with _job_finalize_lock(job.id):
        try:
            db.refresh(job)
        except Exception:
            pass
        if job.status != "pending":
            return job
        return _finalize_pending_job_unlocked(db, job)


def _job_finalize_lock(job_id: int) -> Lock:
    with _FINALIZE_LOCKS_GUARD:
        lock = _FINALIZE_LOCKS.get(job_id)
        if lock is None:
            lock = Lock()
            _FINALIZE_LOCKS[job_id] = lock
        return lock


def _finalize_pending_job_unlocked(db: Session, job: AnalysisJob) -> AnalysisJob:
    analysis_path = _analysis_path(job.id)
    if analysis_path.exists() and analysis_path.stat().st_size > 0:
        _finalize_analysis_file(db, job, analysis_path)
        return job

    exit_code_path = _exit_code_path(job.id)
    if exit_code_path.exists():
        _fail_exited_model_without_analysis(db, job, exit_code_path)
        return job

    if _model_start_tracking_failed(job):
        update_job_failed(
            db,
            job,
            _model_failure_message(job, "model_start", "pid file was not created"),
        )
        return job

    pid = _read_pid(_pid_path(job.id))
    if pid is not None and not _is_process_running(pid) and _model_start_grace_elapsed(job.created_at):
        update_job_failed(
            db,
            job,
            _model_failure_message(job, "model_exit", "monitor process stopped before writing exit code"),
        )
        return job

    if _is_result_timeout(job.created_at):
        update_job_failed(
            db,
            job,
            _model_failure_message(job, "timeout", f"{ANALYSIS_FILENAME} 생성 시간 초과"),
        )
    return job


def _fail_exited_model_without_analysis(db: Session, job: AnalysisJob, exit_code_path: Path) -> None:
    exit_code = _read_text_tail(exit_code_path, 80) or "unknown"
    update_job_failed(
        db,
        job,
        _model_failure_message(
            job,
            "model_exit",
            f"exit_code={exit_code}; {ANALYSIS_FILENAME} was not created",
        ),
    )


def _finalize_analysis_file(db: Session, job: AnalysisJob, analysis_path: Path) -> None:
    try:
        raw = analysis_path.read_text(encoding="utf-8-sig")
    except Exception as exc:
        update_job_failed(db, job, f"parser: {ANALYSIS_FILENAME} 읽기 실패: {exc}")
        return

    if not raw.strip():
        return

    parse_result = parse_markdown(raw)
    if not parse_result.success:
        failed_str = ", ".join(parse_result.failed)
        update_job_failed(
            db,
            job,
            f"parser: [{failed_str}] 필드 누락. 원본 앞 300자: {raw[:300]}",
            raw_markdown=raw,
        )
        return

    ticker = normalize_ticker(job.ticker)
    csv_path = _latest_csv_path(ticker, _job_output_dir(job.id))
    stock_name = _stock_name_from_csv_filename(csv_path, ticker) if csv_path is not None else ""

    try:
        analysis = create_analysis(
            db,
            AnalysisCreate(
                run_id=job.run_id,
                ticker=ticker,
                name=stock_name or ticker,
                model=_analysis_model_for_model(job.model),
                markdown=raw,
                **parse_result.data,
            ),
        )
        update_job_done(db, job, analysis.id, raw_markdown=raw)
    except Exception as exc:
        db.rollback()
        update_job_failed(db, job, f"db: {exc}", raw_markdown=raw)


def _run_pick(ticker: str, stock_name: str, output_dir: Path) -> None:
    if market_for_ticker(ticker) == "US":
        from scripts.pick_us import run_pick_us

        run_pick_us(ticker, years=5, output_dir=str(output_dir), stock_name=stock_name)
        return

    from scripts.pick import run_pick

    run_pick(ticker, years=5, output_dir=str(output_dir), stock_name=stock_name)


def _resolve_stock_name(ticker: str) -> str:
    if market_for_ticker(ticker) == "US":
        from scripts.pick_us import resolve_stock_name

        return resolve_stock_name(ticker)

    from scripts.pick import resolve_stock_name
    return resolve_stock_name(ticker)


def _system_prompt_for_ticker(ticker: str) -> str:
    return US_SYSTEM_PROMPT if market_for_ticker(ticker) == "US" else KR_SYSTEM_PROMPT


def _job_output_dir(job_id: int) -> Path:
    return PICK_OUTPUT_DIR / "jobs" / str(job_id)


def _analysis_path(job_id: int) -> Path:
    return _job_output_dir(job_id) / ANALYSIS_FILENAME


def _pid_path(job_id: int) -> Path:
    return _job_output_dir(job_id) / PID_FILENAME


def _exit_code_path(job_id: int) -> Path:
    return _job_output_dir(job_id) / EXIT_CODE_FILENAME


def _is_result_timeout(created_at: datetime) -> bool:
    now = seoul_now()
    if created_at.tzinfo is None:
        return now.replace(tzinfo=None) - created_at > timedelta(seconds=ANALYSIS_RESULT_TIMEOUT_SECONDS)
    return now - created_at > timedelta(seconds=ANALYSIS_RESULT_TIMEOUT_SECONDS)


def _model_start_grace_elapsed(created_at: datetime) -> bool:
    now = seoul_now()
    if created_at.tzinfo is None:
        return now.replace(tzinfo=None) - created_at > timedelta(seconds=MODEL_START_GRACE_SECONDS)
    return now - created_at > timedelta(seconds=MODEL_START_GRACE_SECONDS)


def _model_start_tracking_failed(job: AnalysisJob) -> bool:
    prompt_path = _job_output_dir(job.id) / PROMPT_FILENAME
    return prompt_path.exists() and not _pid_path(job.id).exists() and _model_start_grace_elapsed(job.created_at)


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _is_windows_process_running(pid)

    try:
        import os

        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _is_windows_process_running(pid: int) -> bool:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        process = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not process:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code)):
                return False
            return exit_code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(process)
    except Exception:
        return True


def _runner_for_model(model: str) -> Callable[..., subprocess.Popen]:
    if model == "codex":
        return _run_codex
    if model == "gemini":
        return _run_gemini
    return _run_claude


def _analysis_model_for_model(model: str | None) -> str:
    if model == "codex":
        return "codex-cli"
    if model == "gemini":
        return "gemini-cli"
    return "claude-code"


def _model_failure_message(job: AnalysisJob, prefix: str, reason: str) -> str:
    log_parts = []
    stdout_tail = _read_text_tail(_job_output_dir(job.id) / STDOUT_LOG_FILENAME)
    stderr_tail = _read_text_tail(_job_output_dir(job.id) / STDERR_LOG_FILENAME)
    if stdout_tail:
        log_parts.append(f"stdout: {stdout_tail}")
    if stderr_tail:
        log_parts.append(f"stderr: {stderr_tail}")

    message = f"{prefix}: {job.model}: {reason}"
    if log_parts:
        message = f"{message}; " + "; ".join(log_parts)
    return message


def _read_text_tail(path: Path, limit: int = LOG_TAIL_CHARS) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text.strip()[-limit:]


def _start_runner(
    runner: Callable[..., subprocess.Popen],
    csv_text: str,
    system_prompt: str,
    analysis_path: Path,
    prompt_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    pid_path: Path,
    exit_code_path: Path,
) -> subprocess.Popen:
    try:
        code = runner.__code__
        accepts_varargs = bool(code.co_flags & 0x04)
        if code.co_argcount >= 8 or accepts_varargs:
            return runner(
                csv_text,
                system_prompt,
                analysis_path,
                prompt_path,
                stdout_path,
                stderr_path,
                pid_path,
                exit_code_path,
            )
        if code.co_argcount >= 6:
            return runner(csv_text, system_prompt, analysis_path, prompt_path, stdout_path, stderr_path)
        if code.co_argcount >= 3:
            return runner(csv_text, system_prompt, analysis_path)
        if code.co_argcount >= 2:
            return runner(csv_text, system_prompt)
    except AttributeError:
        pass
    return runner(csv_text)


def _latest_csv_path(ticker: str, output_dir: Path) -> Path | None:
    files = sorted(output_dir.glob(f"{ticker}_*.csv"), key=lambda path: path.stat().st_mtime)
    if not files:
        return None
    return files[-1]


def _stock_name_from_csv_filename(csv_path: Path, ticker: str) -> str:
    pattern = rf"^{re.escape(ticker)}_(?P<name>.+)_weekly_\d{{8}}$"
    match = re.match(pattern, csv_path.stem)
    if match is None:
        return ""
    return match.group("name").strip()


def _trim_csv(csv_text: str, max_data_rows: int) -> str:
    lines = csv_text.strip().splitlines()
    header, data_rows = lines[0], lines[1:]
    future_rows, hist_rows = data_rows[-26:], data_rows[:-26]
    trimmed = hist_rows[-max_data_rows:] if len(hist_rows) > max_data_rows else hist_rows
    return "\n".join([header] + trimmed + future_rows)


def _claude_cmd() -> list[str]:
    model_flag = ["--model", "sonnet"]
    if sys.platform != "win32":
        return ["claude", "--dangerously-skip-permissions", *model_flag, "-p"]
    # claude.cmd (batch wrapper) doesn't propagate claude.exe exit codes,
    # so batch artifacts ("Active code page", "Terminate batch job") leak into stdout.
    # Call claude.exe directly when available.
    candidates = [
        Path.home() / ".local" / "bin" / "claude.exe",
        Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe",
    ]
    for exe in candidates:
        if exe.exists():
            return [str(exe), "--dangerously-skip-permissions", *model_flag, "-p"]
    return ["claude.cmd", "--dangerously-skip-permissions", *model_flag, "-p"]


def _build_file_output_prompt(system_prompt: str, csv_text: str, analysis_path: Path) -> str:
    return f"""{system_prompt}

추가 지시:
- 최종 분석 마크다운은 stdout에 출력하지 말고 지정된 파일에만 저장하세요.
- 저장 경로: {analysis_path.resolve()}
- UTF-8 텍스트 파일로 저장하세요.
- 파일 내용은 위 출력 형식의 마크다운만 포함해야 하며, 코드블록/설명/요약 문장을 추가하지 마세요.

CSV:
{csv_text}"""


def _spawn_model_process(
    cmd: list[str],
    prompt: str,
    prompt_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    pid_path: Path,
    exit_code_path: Path,
) -> subprocess.Popen:
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt, encoding="utf-8")
    if exit_code_path.exists():
        exit_code_path.unlink()

    payload = json.dumps(
        {
            "cmd": cmd,
            "prompt_path": str(prompt_path.resolve()),
            "stdout_path": str(stdout_path.resolve()),
            "stderr_path": str(stderr_path.resolve()),
            "exit_code_path": str(exit_code_path.resolve()),
        },
        ensure_ascii=True,
    )
    wrapper_cmd = [sys.executable, "-c", _MODEL_PROCESS_WRAPPER, payload]

    popen_kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "text": True,
    }
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess,
            "DETACHED_PROCESS",
            0,
        )
        if creationflags:
            popen_kwargs["creationflags"] = creationflags
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(wrapper_cmd, **popen_kwargs)
    pid_path.write_text(str(process.pid), encoding="utf-8")
    return process


_MODEL_PROCESS_WRAPPER = r"""
import json
import subprocess
import sys
import traceback

payload = json.loads(sys.argv[1])
returncode = 127

try:
    with (
        open(payload["prompt_path"], "r", encoding="utf-8") as stdin_file,
        open(payload["stdout_path"], "w", encoding="utf-8") as stdout_file,
        open(payload["stderr_path"], "w", encoding="utf-8") as stderr_file,
    ):
        popen_kwargs = {"text": True}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            payload["cmd"],
            stdin=stdin_file,
            stdout=stdout_file,
            stderr=stderr_file,
            **popen_kwargs,
        )
        returncode = process.wait()
except Exception as exc:
    try:
        with open(payload["stderr_path"], "a", encoding="utf-8") as stderr_file:
            stderr_file.write("\n[model_start_error] " + str(exc) + "\n")
            stderr_file.write(traceback.format_exc(limit=5))
    except Exception:
        pass
finally:
    try:
        with open(payload["exit_code_path"], "w", encoding="utf-8") as exit_file:
            exit_file.write(str(returncode))
    except Exception:
        pass
"""


def _run_claude(
    csv_text: str,
    system_prompt: str = SYSTEM_PROMPT,
    analysis_path: Path | None = None,
    prompt_path: Path | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    pid_path: Path | None = None,
    exit_code_path: Path | None = None,
) -> subprocess.Popen:
    analysis_path = analysis_path or PICK_OUTPUT_DIR / ANALYSIS_FILENAME
    prompt_path = prompt_path or PICK_OUTPUT_DIR / PROMPT_FILENAME
    stdout_path = stdout_path or PICK_OUTPUT_DIR / STDOUT_LOG_FILENAME
    stderr_path = stderr_path or PICK_OUTPUT_DIR / STDERR_LOG_FILENAME
    pid_path = pid_path or PICK_OUTPUT_DIR / PID_FILENAME
    exit_code_path = exit_code_path or PICK_OUTPUT_DIR / EXIT_CODE_FILENAME
    prompt = _build_file_output_prompt(system_prompt, csv_text, analysis_path)
    return _spawn_model_process(_claude_cmd(), prompt, prompt_path, stdout_path, stderr_path, pid_path, exit_code_path)


def _run_codex(
    csv_text: str,
    system_prompt: str = SYSTEM_PROMPT,
    analysis_path: Path | None = None,
    prompt_path: Path | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    pid_path: Path | None = None,
    exit_code_path: Path | None = None,
) -> subprocess.Popen:
    analysis_path = analysis_path or PICK_OUTPUT_DIR / ANALYSIS_FILENAME
    prompt_path = prompt_path or PICK_OUTPUT_DIR / PROMPT_FILENAME
    stdout_path = stdout_path or PICK_OUTPUT_DIR / STDOUT_LOG_FILENAME
    stderr_path = stderr_path or PICK_OUTPUT_DIR / STDERR_LOG_FILENAME
    pid_path = pid_path or PICK_OUTPUT_DIR / PID_FILENAME
    exit_code_path = exit_code_path or PICK_OUTPUT_DIR / EXIT_CODE_FILENAME
    prompt = _build_file_output_prompt(system_prompt, _trim_csv(csv_text, 200), analysis_path)
    cmd = ["codex.cmd", "exec", "--yolo", "-"] if sys.platform == "win32" else ["codex", "exec", "--yolo", "-"]
    return _spawn_model_process(cmd, prompt, prompt_path, stdout_path, stderr_path, pid_path, exit_code_path)


def _run_gemini(
    csv_text: str,
    system_prompt: str = SYSTEM_PROMPT,
    analysis_path: Path | None = None,
    prompt_path: Path | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    pid_path: Path | None = None,
    exit_code_path: Path | None = None,
) -> subprocess.Popen:
    analysis_path = analysis_path or PICK_OUTPUT_DIR / ANALYSIS_FILENAME
    prompt_path = prompt_path or PICK_OUTPUT_DIR / PROMPT_FILENAME
    stdout_path = stdout_path or PICK_OUTPUT_DIR / STDOUT_LOG_FILENAME
    stderr_path = stderr_path or PICK_OUTPUT_DIR / STDERR_LOG_FILENAME
    pid_path = pid_path or PICK_OUTPUT_DIR / PID_FILENAME
    exit_code_path = exit_code_path or PICK_OUTPUT_DIR / EXIT_CODE_FILENAME
    prompt = _build_file_output_prompt(system_prompt, csv_text, analysis_path)
    # Pass prompt via stdin; -p "" triggers non-interactive (headless) mode
    cmd = (
        ["gemini.cmd", "--yolo", "-p", "", "--output-format", "text"]
        if sys.platform == "win32"
        else ["gemini", "--yolo", "-p", "", "--output-format", "text"]
    )
    return _spawn_model_process(cmd, prompt, prompt_path, stdout_path, stderr_path, pid_path, exit_code_path)
