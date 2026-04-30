from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal, NamedTuple

from sqlalchemy import Select, desc, func, or_, select
from sqlalchemy.orm import Session

from backend.korean_search import extract_korean_initials, is_korean_initial_query
from backend.models import Analysis, AnalysisJob, KrxStock, Run, StockPrice
from backend.parser import parse_entry_candidates
from backend.schemas import AnalysisCreate
from backend.timezone import seoul_now


RUN_ORDER_BY = (desc(Run.created_at), desc(Run.id))
ANALYSIS_ORDER_BY = (desc(Analysis.created_at), desc(Analysis.id))
JOB_ORDER_BY = (desc(AnalysisJob.created_at), desc(AnalysisJob.id))
ENTRY_NEAR_THRESHOLD_PCT = 2.0
EntryCandidateFilter = Literal["all", "pullback", "breakout"]
ENTRY_CANDIDATE_LABELS: dict[EntryCandidateFilter, set[str] | None] = {
    "all": None,
    "pullback": {"눌림"},
    "breakout": {"돌파"},
}


class RunRow(NamedTuple):
    id: int
    memo: str | None
    created_at: datetime
    analysis_count: int


class AnalysisPageRow(NamedTuple):
    items: list["AnalysisSummaryRow"]
    page: int
    page_size: int
    total: int
    total_pages: int


class AnalysisSummaryRow(NamedTuple):
    id: int
    run_id: int
    ticker: str
    name: str
    model: str
    judgment: str
    trend: str
    cloud_position: str
    ma_alignment: str
    created_at: datetime
    entry_price: float | None
    entry_price_max: float | None
    current_price: float | None
    current_price_date: date | None
    entry_gap_pct: float | None
    is_entry_near: bool
    entry_candidates: list["EntryCandidateRow"]


class EntryCandidateRow(NamedTuple):
    label: str
    price: float
    price_max: float | None
    gap_pct: float | None
    is_near: bool


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
        name_initials=extract_korean_initials(obj.name),
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
    entry_gap_lte: float | None = None,
    entry_candidate: EntryCandidateFilter = "all",
    page: int = 1,
    page_size: int = 25,
) -> AnalysisPageRow:
    stmt = _analysis_filter_stmt(judgment=judgment, run_id=run_id, q=q)
    offset = (page - 1) * page_size

    if entry_gap_lte is not None:
        analyses = list(db.scalars(stmt.order_by(*ANALYSIS_ORDER_BY)).all())
        rows = [
            row
            for row in _with_entry_gap(db, analyses)
            if _has_near_entry(row, entry_gap_lte, entry_candidate)
        ]
        rows.sort(
            key=lambda row: (
                _entry_gap_sort_value(row, entry_candidate),
                -row.created_at.timestamp(),
                -row.id,
            )
        )
        total = len(rows)
        items = rows[offset : offset + page_size]
    else:
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        analyses = list(
            db.scalars(stmt.order_by(*ANALYSIS_ORDER_BY).offset(offset).limit(page_size)).all()
        )
        items = _with_entry_gap(db, analyses)

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
            filters = [
                Analysis.ticker.ilike(pattern, escape="\\"),
                Analysis.name.ilike(pattern, escape="\\"),
            ]
            if is_korean_initial_query(query):
                filters.append(Analysis.name_initials.ilike(pattern, escape="\\"))
            stmt = stmt.where(or_(*filters))
    return stmt


def _with_entry_gap(db: Session, analyses: list[Analysis]) -> list[AnalysisSummaryRow]:
    if not analyses:
        return []

    tickers = {analysis.ticker for analysis in analyses}
    prices = {
        price.ticker: price
        for price in db.scalars(select(StockPrice).where(StockPrice.ticker.in_(tickers))).all()
    }

    return [
        _to_analysis_summary_row(analysis, prices.get(analysis.ticker))
        for analysis in analyses
    ]


def _to_analysis_summary_row(
    analysis: Analysis,
    stock_price: StockPrice | None,
) -> AnalysisSummaryRow:
    current_price = stock_price.close_price if stock_price is not None else None
    entry_candidates = _build_entry_candidates(analysis, current_price)
    available_gaps = [
        candidate.gap_pct
        for candidate in entry_candidates
        if candidate.gap_pct is not None
    ]
    entry_gap_pct = min(available_gaps) if available_gaps else calc_entry_gap_pct(
        current_price=current_price,
        entry_price=analysis.entry_price,
        entry_price_max=analysis.entry_price_max,
    )

    return AnalysisSummaryRow(
        id=analysis.id,
        run_id=analysis.run_id,
        ticker=analysis.ticker,
        name=analysis.name,
        model=analysis.model,
        judgment=analysis.judgment,
        trend=analysis.trend,
        cloud_position=analysis.cloud_position,
        ma_alignment=analysis.ma_alignment,
        created_at=analysis.created_at,
        entry_price=analysis.entry_price,
        entry_price_max=analysis.entry_price_max,
        current_price=current_price,
        current_price_date=stock_price.price_date if stock_price is not None else None,
        entry_gap_pct=entry_gap_pct,
        is_entry_near=entry_gap_pct is not None and entry_gap_pct <= ENTRY_NEAR_THRESHOLD_PCT,
        entry_candidates=entry_candidates,
    )


def _build_entry_candidates(
    analysis: Analysis,
    current_price: float | None,
) -> list[EntryCandidateRow]:
    parsed_candidates = [
        (candidate.label, candidate.price, candidate.price_max)
        for candidate in parse_entry_candidates(analysis.markdown)
    ]

    if not parsed_candidates and analysis.entry_price is not None:
        parsed_candidates = [
            ("진입", analysis.entry_price, analysis.entry_price_max),
        ]

    return [
        _build_entry_candidate_row(
            label=label,
            price=price,
            price_max=price_max,
            current_price=current_price,
        )
        for label, price, price_max in parsed_candidates
    ]


def _build_entry_candidate_row(
    label: str,
    price: float,
    price_max: float | None,
    current_price: float | None,
) -> EntryCandidateRow:
    gap_pct = calc_entry_gap_pct(
        current_price=current_price,
        entry_price=price,
        entry_price_max=price_max,
    )
    return EntryCandidateRow(
        label=label,
        price=price,
        price_max=price_max,
        gap_pct=gap_pct,
        is_near=gap_pct is not None and gap_pct <= ENTRY_NEAR_THRESHOLD_PCT,
    )


def _has_near_entry(
    row: AnalysisSummaryRow,
    threshold: float,
    entry_candidate: EntryCandidateFilter = "all",
) -> bool:
    return any(
        gap_pct is not None and gap_pct <= threshold
        for gap_pct in _entry_candidate_gaps(row, entry_candidate)
    )


def _entry_gap_sort_value(
    row: AnalysisSummaryRow,
    entry_candidate: EntryCandidateFilter,
) -> float:
    gaps = [
        gap_pct
        for gap_pct in _entry_candidate_gaps(row, entry_candidate)
        if gap_pct is not None
    ]
    return min(gaps) if gaps else float("inf")


def _entry_candidate_gaps(
    row: AnalysisSummaryRow,
    entry_candidate: EntryCandidateFilter,
) -> list[float | None]:
    labels = ENTRY_CANDIDATE_LABELS[entry_candidate]
    if labels is None:
        candidate_gaps = [candidate.gap_pct for candidate in row.entry_candidates]
        return candidate_gaps or [row.entry_gap_pct]

    return [
        candidate.gap_pct
        for candidate in row.entry_candidates
        if candidate.label in labels
    ]


def calc_entry_gap_pct(
    current_price: float | None,
    entry_price: float | None,
    entry_price_max: float | None,
) -> float | None:
    if current_price is None or current_price <= 0 or entry_price is None:
        return None

    entry_low = min(entry_price, entry_price_max) if entry_price_max is not None else entry_price
    entry_high = max(entry_price, entry_price_max) if entry_price_max is not None else entry_price

    if entry_low <= current_price <= entry_high:
        return 0.0

    nearest_entry = entry_low if current_price < entry_low else entry_high
    return abs(nearest_entry - current_price) / current_price * 100


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


def get_jobs(
    db: Session,
    run_id: int | None = None,
    statuses: list[str] | None = None,
) -> list[AnalysisJob]:
    stmt = select(AnalysisJob)
    if run_id is not None:
        stmt = stmt.where(AnalysisJob.run_id == run_id)
    if statuses:
        stmt = stmt.where(AnalysisJob.status.in_(statuses))
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


_KRX_TTL_HOURS = 24


def search_krx_stocks(db: Session, q: str) -> list[KrxStock]:
    _ensure_krx_listing(db)
    pattern = _escape_like(q)
    if is_korean_initial_query(q):
        return db.query(KrxStock).filter(
            KrxStock.name_initials.ilike(f"{pattern}%", escape="\\")
        ).limit(10).all()
    return db.query(KrxStock).filter(
        KrxStock.name.ilike(f"%{pattern}%", escape="\\")
    ).limit(10).all()


def _ensure_krx_listing(db: Session) -> None:
    latest = db.query(func.max(KrxStock.updated_at)).scalar()
    if latest is None or _is_krx_expired(latest):
        _refresh_krx_listing(db)


def _is_krx_expired(updated_at: datetime) -> bool:
    now = seoul_now()
    if updated_at.tzinfo is None:
        return now.replace(tzinfo=None) - updated_at > timedelta(hours=_KRX_TTL_HOURS)
    return now - updated_at > timedelta(hours=_KRX_TTL_HOURS)


def _refresh_krx_listing(db: Session) -> None:
    import FinanceDataReader as fdr
    df = fdr.StockListing("KRX")
    code_col = next(c for c in df.columns if c in ("Code", "Symbol", "종목코드"))
    name_col = next(c for c in df.columns if c in ("Name", "종목명"))
    df[code_col] = df[code_col].astype(str).str.zfill(6)
    now = seoul_now()
    for _, row in df.iterrows():
        code = str(row[code_col])
        name = str(row[name_col]).strip()
        db.merge(KrxStock(
            code=code,
            name=name,
            name_initials=extract_korean_initials(name),
            updated_at=now,
        ))
    db.commit()
