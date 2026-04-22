from __future__ import annotations

from datetime import date, datetime
from typing import NamedTuple

from sqlalchemy import Select, desc, func, or_, select
from sqlalchemy.orm import Session

from backend.models import Analysis, AnalysisJob, Run, StockPrice
from backend.schemas import AnalysisCreate
from backend.timezone import seoul_now


RUN_ORDER_BY = (desc(Run.created_at), desc(Run.id))
ANALYSIS_ORDER_BY = (desc(Analysis.created_at), desc(Analysis.id))
JOB_ORDER_BY = (desc(AnalysisJob.created_at), desc(AnalysisJob.id))


class RunRow(NamedTuple):
    id: int
    memo: str | None
    created_at: datetime
    analysis_count: int


class AnalysisPageRow(NamedTuple):
    items: list[Analysis]
    page: int
    page_size: int
    total: int
    total_pages: int


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
        entry_price_max=obj.entry_price_max,
        target_price=obj.target_price,
        target_price_max=obj.target_price_max,
        stop_loss=obj.stop_loss,
        stop_loss_max=obj.stop_loss_max,
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
    q: str | None = None,
) -> list[Analysis]:
    stmt = _analysis_filter_stmt(judgment=judgment, run_id=run_id, q=q)
    return list(db.scalars(stmt.order_by(*ANALYSIS_ORDER_BY)).all())


def get_analyses_page(
    db: Session,
    judgment: str | None = None,
    run_id: int | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> AnalysisPageRow:
    stmt = _analysis_filter_stmt(judgment=judgment, run_id=run_id, q=q)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    offset = (page - 1) * page_size
    items = list(
        db.scalars(stmt.order_by(*ANALYSIS_ORDER_BY).offset(offset).limit(page_size)).all()
    )
    total_pages = (total + page_size - 1) // page_size if total else 0
    return AnalysisPageRow(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


def _analysis_filter_stmt(
    judgment: str | None = None,
    run_id: int | None = None,
    q: str | None = None,
) -> Select[tuple[Analysis]]:
    stmt = select(Analysis)
    if judgment is not None:
        stmt = stmt.where(Analysis.judgment == judgment)
    if run_id is not None:
        stmt = stmt.where(Analysis.run_id == run_id)
    if q is not None:
        query = q.strip()
        if query:
            pattern = f"%{_escape_like(query)}%"
            stmt = stmt.where(
                or_(
                    Analysis.ticker.ilike(pattern, escape="\\"),
                    Analysis.name.ilike(pattern, escape="\\"),
                )
            )
    return stmt


def get_analysis(db: Session, analysis_id: int) -> Analysis | None:
    stmt = select(Analysis).where(Analysis.id == analysis_id)
    return db.scalars(stmt).first()


def get_analysis_history(db: Session, ticker: str) -> list[Analysis]:
    stmt = select(Analysis).where(Analysis.ticker == ticker).order_by(*ANALYSIS_ORDER_BY)
    return list(db.scalars(stmt).all())


def create_job(db: Session, ticker: str, run_id: int, model: str = "claude") -> AnalysisJob:
    job = AnalysisJob(ticker=ticker, run_id=run_id, model=model, status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: int) -> AnalysisJob | None:
    return db.get(AnalysisJob, job_id)


def get_jobs(db: Session, run_id: int | None = None) -> list[AnalysisJob]:
    stmt = select(AnalysisJob)
    if run_id is not None:
        stmt = stmt.where(AnalysisJob.run_id == run_id)
    return list(db.scalars(stmt.order_by(*JOB_ORDER_BY)).all())


def update_job_done(db: Session, job: AnalysisJob, analysis_id: int, raw_markdown: str | None = None) -> None:
    job.status = "done"
    job.analysis_id = analysis_id
    job.error_message = None
    job.raw_markdown = raw_markdown
    db.commit()
    db.refresh(job)


def update_job_failed(db: Session, job: AnalysisJob, error_message: str, raw_markdown: str | None = None) -> None:
    job.status = "failed"
    job.error_message = error_message
    job.raw_markdown = raw_markdown
    db.commit()
    db.refresh(job)


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
    row.fetched_at = seoul_now()
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


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
