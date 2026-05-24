from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models import BacktestRun, BacktestSignal, BacktestStat
from backend.schemas import (
    BacktestHistogram,
    BacktestRunDetail,
    BacktestRunSummary,
    BacktestSignalPage,
    BacktestSignalRead,
    BacktestStatRead,
    HistogramBin,
)

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

_RET_COLUMN = {
    4: BacktestSignal.ret_4w,
    8: BacktestSignal.ret_8w,
    12: BacktestSignal.ret_12w,
    26: BacktestSignal.ret_26w,
}


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


@router.get("/runs", response_model=list[BacktestRunSummary])
def list_runs(db: Session = Depends(get_db)) -> list[BacktestRunSummary]:
    runs = list(
        db.scalars(
            select(BacktestRun)
            .options(joinedload(BacktestRun.source_analysis))
            .order_by(BacktestRun.id.desc())
        ).all()
    )
    adj = _adj_signal_counts(db, [run.id for run in runs])
    result = []
    for run in runs:
        summary = BacktestRunSummary.model_validate(run)
        if run.id in adj:
            summary.signal_count = adj[run.id]
        if run.source_analysis is not None:
            summary.source_ticker = run.source_analysis.ticker
            summary.source_name = run.source_analysis.name
        result.append(summary)
    return result


@router.get("/runs/{run_id}", response_model=BacktestRunDetail)
def get_run(run_id: int, db: Session = Depends(get_db)) -> BacktestRunDetail:
    run = db.scalar(
        select(BacktestRun)
        .options(joinedload(BacktestRun.source_analysis))
        .where(BacktestRun.id == run_id)
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
    if run.source_analysis is not None:
        summary.source_ticker = run.source_analysis.ticker
        summary.source_name = run.source_analysis.name
    return BacktestRunDetail(
        **summary.model_dump(),
        stats=[BacktestStatRead.model_validate(stat) for stat in stats],
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
