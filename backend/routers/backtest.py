from __future__ import annotations

import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database import SessionLocal, get_db
from backend.models import (
    Analysis,
    BacktestPreloadJob,
    BacktestRun,
    BacktestSignal,
    BacktestStat,
    BacktestUniverseMember,
)
from backend.schemas import (
    BacktestEventSummary,
    BacktestHistogram,
    BacktestRunDetail,
    BacktestRunSummary,
    BacktestSignalPage,
    BacktestSignalRead,
    BacktestStatRead,
    BacktestUniverseMemberCreate,
    BacktestUniverseMemberRead,
    BacktestUniverseMemberUpdate,
    HistogramBin,
)
from backend.timezone import seoul_now
from scripts.backtest.preload_daily import preload_daily_bars
from scripts.backtest.universe import normalize_korean_ticker

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

_RET_COLUMN = {
    4: BacktestSignal.ret_4w,
    8: BacktestSignal.ret_8w,
    12: BacktestSignal.ret_12w,
    26: BacktestSignal.ret_26w,
}
_ACTIVE_PRELOAD_JOB_STATUSES = ("pending", "running")


def _universe_member_or_404(db: Session, ticker: str) -> BacktestUniverseMember:
    normalized = _normalize_universe_ticker(ticker)
    member = db.get(BacktestUniverseMember, normalized)
    if member is None:
        raise HTTPException(status_code=404, detail="Backtest universe member not found")
    return member


def _normalize_universe_ticker(ticker: str) -> str:
    try:
        return normalize_korean_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _create_preload_job_if_needed(
    db: Session,
    member: BacktestUniverseMember,
) -> BacktestPreloadJob | None:
    existing_job = db.scalar(
        select(BacktestPreloadJob)
        .where(
            BacktestPreloadJob.ticker == member.ticker,
            BacktestPreloadJob.status.in_(_ACTIVE_PRELOAD_JOB_STATUSES),
        )
        .order_by(BacktestPreloadJob.id.desc())
    )
    if existing_job is not None:
        return None

    preload_job = BacktestPreloadJob(ticker=member.ticker, name=member.name)
    db.add(preload_job)
    db.flush()
    return preload_job


@router.get("/universe", response_model=list[BacktestUniverseMemberRead])
def list_universe_members(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
) -> list[BacktestUniverseMemberRead]:
    stmt = select(BacktestUniverseMember).where(BacktestUniverseMember.market == "KR")
    if not include_inactive:
        stmt = stmt.where(BacktestUniverseMember.active.is_(True))
    members = list(
        db.scalars(
            stmt.order_by(BacktestUniverseMember.sort_order, BacktestUniverseMember.ticker)
        ).all()
    )
    return [BacktestUniverseMemberRead.model_validate(member) for member in members]


@router.post(
    "/universe",
    response_model=BacktestUniverseMemberRead,
    status_code=status.HTTP_201_CREATED,
)
def create_universe_member(
    payload: BacktestUniverseMemberCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> BacktestUniverseMemberRead:
    ticker = _normalize_universe_ticker(payload.ticker)
    if db.get(BacktestUniverseMember, ticker) is not None:
        raise HTTPException(status_code=409, detail="Backtest universe member already exists")

    member = BacktestUniverseMember(
        ticker=ticker,
        name=payload.name.strip(),
        market=payload.market,
        active=payload.active,
        sort_order=payload.sort_order,
        source=payload.source.strip() or "manual",
    )
    db.add(member)
    db.flush()
    preload_job = _create_preload_job_if_needed(db, member)
    preload_job_id = preload_job.id if preload_job is not None else None
    db.commit()
    db.refresh(member)
    if preload_job_id is not None:
        background_tasks.add_task(run_backtest_preload_pipeline, preload_job_id)
    return BacktestUniverseMemberRead.model_validate(member)


def run_backtest_preload_pipeline(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(BacktestPreloadJob, job_id)
        if job is None:
            return

        job.status = "running"
        db.commit()

        result = preload_daily_bars(db, universe=[(job.ticker, job.name)])
        job.processed = result.processed
        job.skipped = result.skipped
        job.upserted_rows = result.upserted_rows
        job.completed_at = seoul_now()
        if result.failed:
            job.status = "failed"
            job.error_message = "; ".join(
                f"{ticker} {name}: {message}" for ticker, name, message in result.failed
            )
        else:
            job.status = "done"
            job.error_message = None
        db.commit()
    except Exception as exc:
        job = db.get(BacktestPreloadJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = seoul_now()
            db.commit()
    finally:
        db.close()


@router.patch("/universe/{ticker}", response_model=BacktestUniverseMemberRead)
def update_universe_member(
    ticker: str,
    payload: BacktestUniverseMemberUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> BacktestUniverseMemberRead:
    member = _universe_member_or_404(db, ticker)
    was_active = member.active
    if payload.name is not None:
        member.name = payload.name.strip()
    if payload.active is not None:
        member.active = payload.active
    if payload.sort_order is not None:
        member.sort_order = payload.sort_order
    preload_job = None
    if payload.active is True and not was_active:
        preload_job = _create_preload_job_if_needed(db, member)
    preload_job_id = preload_job.id if preload_job is not None else None
    db.commit()
    db.refresh(member)
    if preload_job_id is not None:
        background_tasks.add_task(run_backtest_preload_pipeline, preload_job_id)
    return BacktestUniverseMemberRead.model_validate(member)


@router.delete("/universe/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
def delete_universe_member(
    ticker: str,
    db: Session = Depends(get_db),
) -> Response:
    member = _universe_member_or_404(db, ticker)
    member.active = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _adj_signal_counts(db: Session, run_ids: list[int]) -> dict[int, int]:
    """H4 기준 8-9 버킷 제외한 신호 수를 run_id별로 반환."""
    if not run_ids:
        return {}
    rows = db.execute(
        select(BacktestStat.run_id, func.sum(BacktestStat.count))
        .where(
            BacktestStat.run_id.in_(run_ids),
            BacktestStat.horizon == 4,
            BacktestStat.score_bucket.not_in(["ALL", "8-9"]),
        )
        .group_by(BacktestStat.run_id)
    ).all()
    return {row[0]: int(row[1]) for row in rows}


def _planned_contract_returns(
    analysis: Analysis | None,
) -> tuple[float | None, float | None, float | None]:
    if (
        analysis is None
        or analysis.entry_price is None
        or analysis.target_price is None
        or analysis.stop_loss is None
        or analysis.entry_price <= 0
    ):
        return None, None, None

    target_return = analysis.target_price / analysis.entry_price - 1
    stop_return = analysis.stop_loss / analysis.entry_price - 1
    risk = abs(stop_return)
    risk_reward = target_return / risk if risk > 0 else None
    return target_return, stop_return, risk_reward


def _event_summary(db: Session, run: BacktestRun) -> BacktestEventSummary:
    signals = list(
        db.scalars(
            select(BacktestSignal).where(BacktestSignal.run_id == run.id)
        ).all()
    )
    entered = [signal for signal in signals if signal.exit_reason != "no_entry"]
    returns = [signal.event_return for signal in entered if signal.event_return is not None]
    gains = [event_return for event_return in returns if event_return > 0]
    losses = [event_return for event_return in returns if event_return < 0]
    days = [signal.days_held for signal in entered if signal.days_held is not None]
    target_count = sum(1 for signal in signals if signal.exit_reason == "target")
    stop_count = sum(1 for signal in signals if signal.exit_reason == "stop")
    expiry_count = sum(1 for signal in signals if signal.exit_reason == "expiry")
    no_entry_count = sum(1 for signal in signals if signal.exit_reason == "no_entry")
    mean_return = float(np.mean(returns)) if returns else None
    avg_gain_return = float(np.mean(gains)) if gains else None
    avg_loss_return = float(np.mean(losses)) if losses else None
    realized_payoff_ratio = (
        avg_gain_return / abs(avg_loss_return)
        if avg_gain_return is not None and avg_loss_return is not None and avg_loss_return != 0
        else None
    )
    source_analysis = db.get(Analysis, run.source_analysis_id) if run.source_analysis_id else None
    planned_target_return, planned_stop_return, planned_risk_reward_ratio = (
        _planned_contract_returns(source_analysis)
    )
    target_hit_rate = (target_count / len(entered)) if entered else None
    positive_return_rate = (
        sum(1 for event_return in returns if event_return > 0) / len(returns)
        if returns
        else None
    )
    return BacktestEventSummary(
        signal_count=len(signals),
        entered_count=len(entered),
        no_entry_count=no_entry_count,
        target_count=target_count,
        stop_count=stop_count,
        expiry_count=expiry_count,
        target_hit_rate=target_hit_rate,
        positive_return_rate=positive_return_rate,
        win_rate=target_hit_rate,
        mean_return=mean_return,
        expectancy=mean_return,
        median_return=float(np.median(returns)) if returns else None,
        avg_days_held=float(np.mean(days)) if days else None,
        planned_target_return=planned_target_return,
        planned_stop_return=planned_stop_return,
        planned_risk_reward_ratio=planned_risk_reward_ratio,
        avg_gain_return=avg_gain_return,
        avg_loss_return=avg_loss_return,
        realized_payoff_ratio=realized_payoff_ratio,
    )


@router.get("/runs", response_model=list[BacktestRunSummary])
def list_runs(db: Session = Depends(get_db)) -> list[BacktestRunSummary]:
    runs = list(
        db.scalars(
            select(BacktestRun).order_by(BacktestRun.id.desc())
        ).all()
    )
    adj = _adj_signal_counts(db, [run.id for run in runs])
    result = []
    for run in runs:
        summary = BacktestRunSummary.model_validate(run)
        if run.id in adj:
            summary.signal_count = adj[run.id]
        if run.source_analysis_id is not None:
            analysis = db.get(Analysis, run.source_analysis_id)
            if analysis is not None:
                summary.source_ticker = analysis.ticker
                summary.source_name = analysis.name
        result.append(summary)
    return result


@router.get("/runs/{run_id}", response_model=BacktestRunDetail)
def get_run(run_id: int, db: Session = Depends(get_db)) -> BacktestRunDetail:
    run = db.scalar(
        select(BacktestRun).where(BacktestRun.id == run_id)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="백테스트 실행을 찾을 수 없습니다.")

    stats = list(
        db.scalars(
            select(BacktestStat)
            .where(BacktestStat.run_id == run_id)
            .order_by(BacktestStat.horizon, BacktestStat.score_bucket)
        ).all()
    )
    summary = BacktestRunSummary.model_validate(run)
    adj = _adj_signal_counts(db, [run_id])
    if run_id in adj:
        summary.signal_count = adj[run_id]
    if run.source_analysis_id is not None:
        analysis = db.get(Analysis, run.source_analysis_id)
        if analysis is not None:
            summary.source_ticker = analysis.ticker
            summary.source_name = analysis.name
    return BacktestRunDetail(
        **summary.model_dump(),
        stats=[BacktestStatRead.model_validate(stat) for stat in stats],
        event_summary=_event_summary(db, run) if run.strategy_kind == "analysis_contract" else None,
    )


@router.get("/runs/{run_id}/signals", response_model=BacktestSignalPage)
def list_signals(
    run_id: int,
    ticker: str | None = None,
    score_bucket: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> BacktestSignalPage:
    if db.get(BacktestRun, run_id) is None:
        raise HTTPException(status_code=404, detail="백테스트 실행을 찾을 수 없습니다.")

    stmt = select(BacktestSignal).where(BacktestSignal.run_id == run_id)
    if ticker:
        stmt = stmt.where(BacktestSignal.ticker == ticker)
    if score_bucket:
        stmt = stmt.where(BacktestSignal.score_bucket == score_bucket)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(db.scalar(total_stmt) or 0)
    items = list(
        db.scalars(
            stmt.order_by(BacktestSignal.signal_date, BacktestSignal.id).offset(offset).limit(limit)
        ).all()
    )
    return BacktestSignalPage(
        total=total,
        items=[BacktestSignalRead.model_validate(item) for item in items],
    )


@router.get("/runs/{run_id}/histogram", response_model=BacktestHistogram)
def get_histogram(
    run_id: int,
    horizon: int = Query(4),
    score_bucket: str = Query("ALL"),
    bins: int = Query(20, ge=5, le=60),
    db: Session = Depends(get_db),
) -> BacktestHistogram:
    if db.get(BacktestRun, run_id) is None:
        raise HTTPException(status_code=404, detail="백테스트 실행을 찾을 수 없습니다.")

    column = _RET_COLUMN.get(horizon)
    if column is None:
        raise HTTPException(status_code=400, detail="지원하지 않는 horizon")

    stmt = select(column).where(BacktestSignal.run_id == run_id, column.is_not(None))
    if score_bucket != "ALL":
        stmt = stmt.where(BacktestSignal.score_bucket == score_bucket)

    values = [float(value) for value in db.scalars(stmt).all()]
    if not values:
        return BacktestHistogram(horizon=horizon, score_bucket=score_bucket, bins=[])

    counts, edges = np.histogram(np.array(values), bins=bins)
    return BacktestHistogram(
        horizon=horizon,
        score_bucket=score_bucket,
        bins=[
            HistogramBin(lower=float(edges[index]), upper=float(edges[index + 1]), count=int(counts[index]))
            for index in range(len(counts))
        ],
    )
