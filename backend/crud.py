from __future__ import annotations

from sqlalchemy import Select, desc, func, select
from sqlalchemy.orm import Session

from backend.models import Analysis, Run
from backend.schemas import AnalysisCreate


RUN_ORDER_BY = (desc(Run.created_at), desc(Run.id))
ANALYSIS_ORDER_BY = (desc(Analysis.created_at), desc(Analysis.id))


def create_run(db: Session, memo: str | None = None) -> Run:
    run = Run(memo=memo)
    db.add(run)
    db.commit()
    db.refresh(run)
    setattr(run, "analysis_count", 0)
    return run


def get_runs(db: Session) -> list[Run]:
    rows = db.execute(_run_with_count_stmt()).all()
    runs: list[Run] = []
    for run, analysis_count in rows:
        setattr(run, "analysis_count", analysis_count)
        runs.append(run)
    return runs


def get_run(db: Session, run_id: int) -> Run | None:
    row = db.execute(_run_with_count_stmt().where(Run.id == run_id)).first()
    if row is None:
        return None

    run, analysis_count = row
    setattr(run, "analysis_count", analysis_count)
    return run


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
    stmt = select(Analysis).where(Analysis.run_id == run_id)
    if judgment is not None:
        stmt = stmt.where(Analysis.judgment == judgment)
    return list(db.scalars(stmt.order_by(*ANALYSIS_ORDER_BY)).all())


def get_analysis(db: Session, analysis_id: int) -> Analysis | None:
    stmt = select(Analysis).where(Analysis.id == analysis_id)
    return db.scalars(stmt).first()


def get_analysis_history(db: Session, ticker: str) -> list[Analysis]:
    stmt = select(Analysis).where(Analysis.ticker == ticker).order_by(*ANALYSIS_ORDER_BY)
    return list(db.scalars(stmt).all())


def _run_with_count_stmt() -> Select[tuple[Run, int]]:
    return (
        select(Run, func.count(Analysis.id).label("analysis_count"))
        .outerjoin(Analysis, Analysis.run_id == Run.id)
        .group_by(Run.id)
        .order_by(*RUN_ORDER_BY)
    )


