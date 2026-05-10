from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from models import Analysis, StockPrice
from schemas import AnalysesPage, AnalysisItem, StockSummary


@dataclass
class _AnalysesResult:
    items: list[Analysis]
    total: int


def list_analyses(
    db: Session,
    *,
    judgment: str | None,
    q: str | None,
    page: int,
    per_page: int,
) -> AnalysesPage:
    query = db.query(Analysis)

    if judgment:
        query = query.filter(Analysis.judgment == judgment)

    if q:
        pattern = f"%{q}%"
        query = query.filter(
            Analysis.name.ilike(pattern)
            | Analysis.name_initials.ilike(pattern)
            | Analysis.ticker.ilike(pattern)
        )

    total = query.count()
    rows = (
        query.outerjoin(StockPrice, Analysis.ticker == StockPrice.ticker)
        .add_columns(StockPrice.close_price, StockPrice.price_date)
        .order_by(Analysis.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    total_pages = max(1, math.ceil(total / per_page))

    items = []
    for a, close_price, price_date in rows:
        item = AnalysisItem.model_validate(a)
        item.current_price = close_price
        item.current_price_date = price_date
        items.append(item)

    return AnalysesPage(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


def get_analysis(db: Session, analysis_id: int) -> tuple[Analysis, float | None, date | None] | None:
    row = (
        db.query(Analysis, StockPrice.close_price, StockPrice.price_date)
        .outerjoin(StockPrice, Analysis.ticker == StockPrice.ticker)
        .filter(Analysis.id == analysis_id)
        .first()
    )
    return row


def list_stock_summary(db: Session) -> list[StockSummary]:
    rows = (
        db.query(
            Analysis.ticker,
            Analysis.name,
            func.sum(case((Analysis.judgment == "매수", 1), else_=0)).label("buy_count"),
            func.sum(case((Analysis.judgment == "홀드", 1), else_=0)).label("hold_count"),
            func.sum(case((Analysis.judgment == "매도", 1), else_=0)).label("sell_count"),
            func.max(Analysis.created_at).label("latest_at"),
        )
        .group_by(Analysis.ticker, Analysis.name)
        .order_by(func.max(Analysis.created_at).desc())
        .all()
    )

    return [
        StockSummary(
            ticker=r.ticker,
            name=r.name,
            buy_count=r.buy_count,
            hold_count=r.hold_count,
            sell_count=r.sell_count,
            latest_at=r.latest_at,
        )
        for r in rows
    ]
