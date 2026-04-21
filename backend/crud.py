from __future__ import annotations

from datetime import date, datetime
from typing import NamedTuple

from sqlalchemy import Select, desc, func, select
from sqlalchemy.orm import Session

from backend.models import Analysis, Run, StockPrice
from backend.schemas import AnalysisCreate


RUN_ORDER_BY = (desc(Run.created_at), desc(Run.id))
ANALYSIS_ORDER_BY = (desc(Analysis.created_at), desc(Analysis.id))


class RunRow(NamedTuple):
    id: int
    memo: str | None
    created_at: datetime
    analysis_count: int


def create_run(db: Session, memo: str | None = None) -> RunRow:
    run = Run(memo=memo)
    db.add(run)
    db.commit()
    db.refresh(run)
    return RunRow(id=run.id, memo=run.memo, created_at=run.created_at, analysis_count=0)


def get_runs(db: Session) -> list[RunRow]:
    rows = db.execute(_run_with_count_stmt()).all()
    return [RunRow(id=run.id, memo=run.memo, created_at=run.created_at, analysis_count=count) for run, count in rows]


def get_run(db: Session, run_id: int) -> RunRow | None:
    row = db.execute(_run_with_count_stmt().where(Run.id == run_id)).first()
    if row is None:
        return None
    run, count = row
    return RunRow(id=run.id, memo=run.memo, created_at=run.created_at, analysis_count=count)


def create_analysis(db: Session, obj: AnalysisCreate) -> Analysis:
    analysis = Analysis(
        run_id=obj.run_id,
        ticker=obj.ticker,
        name=obj.name,
        model=obj.model,
        markdown=obj.markdown,
        judgment=obj.judgment,
        trend=obj.trend,
        cloud_position=obj.cloud_position,
        ma_alignment=obj.ma_alignment,
        entry_price=obj.entry_price,
        target_price=obj.target_price,
        stop_loss=obj.stop_loss,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def get_analyses_by_run(
    db: Session,
    run_id: int,
    judgment: str | None = None,
) -> list[Analysis]:
    return get_analyses(db, judgment=judgment, run_id=run_id)


def get_analyses(
    db: Session,
    judgment: str | None = None,
    run_id: int | None = None,
) -> list[Analysis]:
    stmt = select(Analysis)
    if judgment is not None:
        stmt = stmt.where(Analysis.judgment == judgment)
    if run_id is not None:
        stmt = stmt.where(Analysis.run_id == run_id)
    return list(db.scalars(stmt.order_by(*ANALYSIS_ORDER_BY)).all())


def get_analysis(db: Session, analysis_id: int) -> Analysis | None:
    stmt = select(Analysis).where(Analysis.id == analysis_id)
    return db.scalars(stmt).first()


def get_analysis_history(db: Session, ticker: str) -> list[Analysis]:
    stmt = select(Analysis).where(Analysis.ticker == ticker).order_by(*ANALYSIS_ORDER_BY)
    return list(db.scalars(stmt).all())


def get_stock_price(db: Session, ticker: str) -> StockPrice | None:
    return db.get(StockPrice, ticker)


def upsert_stock_price(
    db: Session,
    ticker: str,
    price_date: date,
    close_price: float,
) -> StockPrice:
    row = db.get(StockPrice, ticker)
    if row is None:
        row = StockPrice(ticker=ticker)
        db.add(row)
    row.price_date = price_date
    row.close_price = close_price
    row.fetched_at = datetime.now().astimezone()
    db.commit()
    db.refresh(row)
    return row


def _run_with_count_stmt() -> Select[tuple[Run, int]]:
    return (
        select(Run, func.count(Analysis.id).label("analysis_count"))
        .outerjoin(Analysis, Analysis.run_id == Run.id)
        .group_by(Run.id)
        .order_by(*RUN_ORDER_BY)
    )

