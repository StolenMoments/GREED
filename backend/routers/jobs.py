from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.crud import create_analysis, create_job, get_job, get_run, update_job_done, update_job_failed
from backend.database import SessionLocal, get_db
from backend.parser import parse_markdown
from backend.schemas import AnalysisCreate, JobRead, JobTriggerRequest


SYSTEM_PROMPT = """당신은 한국 주식 기술적 분석 전문가입니다.
아래 주봉 CSV 데이터를 분석하여 다음 형식으로 응답하세요.

## 판단
**매수** 또는 **홀드** 또는 **매도** 중 하나를 굵게 표시.

## 기술적 지표 요약
- 추세: 상승 또는 하락 또는 횡보
- 구름대 위치: 구름 위 또는 구름 안 또는 구름 아래
- MA 배열: 정배열 또는 역배열 또는 혼조

## 매매 전략
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 진입 조건 | (설명) | 000,000 |
| 1차 목표 | (설명) | 000,000 |
| 손절 기준 | (설명) | 000,000 |

## 분석 근거
(자유 서술)"""

CLAUDE_TIMEOUT_SECONDS = 180
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
    job = create_job(db, ticker=ticker, run_id=payload.run_id)
    background_tasks.add_task(run_analysis_pipeline, job.id)
    return job


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
        try:
            stock_name = _resolve_stock_name(ticker)
            _run_pick(ticker, stock_name)
        except Exception as exc:
            update_job_failed(db, job, f"pick: {exc}")
            return

        csv_path = _latest_csv_path(ticker)
        if csv_path is None:
            update_job_failed(db, job, "pick: CSV 파일 생성 안 됨")
            return

        try:
            csv_text = csv_path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            update_job_failed(db, job, f"pick: {exc}")
            return
        try:
            raw = _run_claude(csv_text)
        except subprocess.TimeoutExpired:
            update_job_failed(db, job, "claude: 180s 타임아웃 초과")
            return
        except RuntimeError as exc:
            update_job_failed(db, job, f"claude: {str(exc)[:300]}")
            return

        if not raw:
            update_job_failed(db, job, "claude: 빈 응답 반환")
            return

        parse_result = parse_markdown(raw)
        if not parse_result.success:
            failed_str = ", ".join(parse_result.failed)
            update_job_failed(db, job, f"parser: [{failed_str}] 필드 누락. 원본 앞 300자: {raw[:300]}")
            return

        try:
            analysis = create_analysis(
                db,
                AnalysisCreate(
                    run_id=job.run_id,
                    ticker=ticker,
                    name=stock_name or ticker,
                    model="claude-code",
                    markdown=raw,
                    **parse_result.data,
                ),
            )
            update_job_done(db, job, analysis.id)
        except Exception as exc:
            db.rollback()
            update_job_failed(db, job, f"db: {exc}")
    finally:
        db.close()


def _run_pick(ticker: str, stock_name: str) -> None:
    from scripts.pick import run_pick

    run_pick(ticker, years=5, output_dir=str(PICK_OUTPUT_DIR), stock_name=stock_name)


def _resolve_stock_name(ticker: str) -> str:
    from scripts.pick import resolve_stock_name

    return resolve_stock_name(ticker)


def _latest_csv_path(ticker: str) -> Path | None:
    files = sorted(PICK_OUTPUT_DIR.glob(f"{ticker}_*.csv"), key=lambda path: path.stat().st_mtime)
    if not files:
        return None
    return files[-1]


def _run_claude(csv_text: str) -> str:
    prompt = f"{SYSTEM_PROMPT}\n\n{csv_text}"
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=CLAUDE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:300])
    return result.stdout.strip()
