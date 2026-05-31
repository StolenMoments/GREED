from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database import SessionLocal, get_db
from backend.models import Analysis, CandidateScanJob, CurrentCandidate
from backend.schemas import CandidateRead, CandidateScanJobCreate, CandidateScanJobRead, ScanSummaryItem
from backend.timezone import seoul_now

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


# ── CRUD helpers ──────────────────────────────────────────────────────────────

def _create_job(db: Session, analysis_id: int, threshold: int) -> CandidateScanJob:
    job = CandidateScanJob(analysis_id=analysis_id, threshold=threshold)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _mark_running(db: Session, job: CandidateScanJob) -> None:
    job.status = "running"
    db.commit()


def _mark_done(db: Session, job: CandidateScanJob, scan_date, count: int) -> None:
    job.status = "done"
    job.scan_date = scan_date
    job.candidate_count = count
    job.completed_at = seoul_now()
    db.commit()


def _mark_failed(db: Session, job: CandidateScanJob, error: str) -> None:
    job.status = "failed"
    job.error_message = error
    job.completed_at = seoul_now()
    db.commit()


# ── Background pipeline ───────────────────────────────────────────────────────

def run_candidate_scan_pipeline(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(CandidateScanJob, job_id)
        if job is None:
            return
        analysis = db.get(Analysis, job.analysis_id)
        if analysis is None:
            _mark_failed(db, job, "Analysis not found")
            return
        try:
            _mark_running(db, job)
            from scripts.backtest.analysis_similarity import scan_current_candidates

            candidates, scan_date = scan_current_candidates(
                db, analysis, threshold=job.threshold
            )
            db.query(CurrentCandidate).filter(
                CurrentCandidate.analysis_id == job.analysis_id,
                CurrentCandidate.scan_date == scan_date,
            ).delete()
            for c in candidates:
                db.add(CurrentCandidate(
                    analysis_id=job.analysis_id,
                    scan_date=scan_date,
                    ticker=c.ticker,
                    name=c.name,
                    score=c.score,
                    current_close=c.current_close,
                    entry_price=c.entry_price,
                    target_price=c.target_price,
                    stop_price=c.stop_price,
                    entry_gap_pct=c.entry_gap_pct,
                ))
            _mark_done(db, job, scan_date, len(candidates))
        except Exception as exc:
            db.rollback()
            fresh = db.get(CandidateScanJob, job_id)
            if fresh is not None:
                _mark_failed(db, fresh, str(exc))
    finally:
        db.close()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/scan/{analysis_id}",
    response_model=CandidateScanJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_scan(
    analysis_id: int,
    payload: CandidateScanJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> CandidateScanJob:
    if db.get(Analysis, analysis_id) is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    job = _create_job(db, analysis_id, payload.threshold)
    background_tasks.add_task(run_candidate_scan_pipeline, job.id)
    return job


@router.get("/scan-jobs/{analysis_id}", response_model=list[CandidateScanJobRead])
def list_scan_jobs(
    analysis_id: int,
    db: Session = Depends(get_db),
) -> list[CandidateScanJob]:
    return (
        db.query(CandidateScanJob)
        .filter(CandidateScanJob.analysis_id == analysis_id)
        .order_by(CandidateScanJob.created_at.desc())
        .limit(20)
        .all()
    )


@router.get("/scan-jobs/{analysis_id}/{job_id}", response_model=CandidateScanJobRead)
def get_scan_job(
    analysis_id: int,
    job_id: int,
    db: Session = Depends(get_db),
) -> CandidateScanJob:
    job = db.get(CandidateScanJob, job_id)
    if job is None or job.analysis_id != analysis_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/scan-summary", response_model=list[ScanSummaryItem])
def list_scan_summary(db: Session = Depends(get_db)) -> list[ScanSummaryItem]:
    latest_sq = (
        select(CandidateScanJob.analysis_id, func.max(CandidateScanJob.id).label("max_id"))
        .group_by(CandidateScanJob.analysis_id)
        .subquery()
    )
    stmt = (
        select(CandidateScanJob, Analysis)
        .join(latest_sq, CandidateScanJob.id == latest_sq.c.max_id)
        .join(Analysis, Analysis.id == CandidateScanJob.analysis_id)
        .order_by(CandidateScanJob.created_at.desc())
    )
    return [
        ScanSummaryItem(
            analysis_id=analysis.id,
            ticker=analysis.ticker,
            name=analysis.name,
            latest_scan_date=job.scan_date,
            threshold=job.threshold,
            candidate_count=job.candidate_count,
            status=job.status,
            latest_job_id=job.id,
        )
        for job, analysis in db.execute(stmt).all()
    ]


@router.get("", response_model=list[CandidateRead])
def list_candidates(
    analysis_id: int,
    min_score: int = 12,
    db: Session = Depends(get_db),
) -> list[CurrentCandidate]:
    return (
        db.query(CurrentCandidate)
        .filter(
            CurrentCandidate.analysis_id == analysis_id,
            CurrentCandidate.score >= min_score,
        )
        .order_by(
            CurrentCandidate.scan_date.desc(),
            CurrentCandidate.score.desc(),
            CurrentCandidate.entry_gap_pct.asc(),
        )
        .all()
    )
