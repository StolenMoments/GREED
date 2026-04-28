from __future__ import annotations

from sqlalchemy import case, func
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends

from backend.database import get_db
from backend.models import Analysis
from backend.schemas import StockSummaryRead

router = APIRouter(tags=["stocks"])


@router.get("/api/stocks/summary", response_model=list[StockSummaryRead])
def stock_summary(db: Session = Depends(get_db)) -> list[StockSummaryRead]:
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
        .order_by(Analysis.name)
        .all()
    )
    return [
        StockSummaryRead(
            ticker=row.ticker,
            name=row.name,
            buy_count=row.buy_count,
            hold_count=row.hold_count,
            sell_count=row.sell_count,
            latest_at=row.latest_at,
        )
        for row in rows
    ]
