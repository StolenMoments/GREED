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
            Analysis.name_initials,
            func.sum(case((Analysis.judgment == "매수", 1), else_=0)).label("buy_count"),
            func.sum(case((Analysis.judgment == "홀드", 1), else_=0)).label("hold_count"),
            func.sum(case((Analysis.judgment == "매도", 1), else_=0)).label("sell_count"),
            func.sum(case((Analysis.outcome == "목표달성", 1), else_=0)).label(
                "target_reached_count"
            ),
            func.sum(case((Analysis.outcome == "진행중", 1), else_=0)).label(
                "ongoing_count"
            ),
            func.sum(case((Analysis.outcome == "손절", 1), else_=0)).label(
                "stop_loss_count"
            ),
            func.max(Analysis.created_at).label("latest_at"),
        )
        .group_by(Analysis.ticker, Analysis.name, Analysis.name_initials)
        .order_by(func.max(Analysis.created_at).desc(), Analysis.name)
        .all()
    )
    return [
        StockSummaryRead(
            ticker=row.ticker,
            name=row.name,
            name_initials=row.name_initials,
            buy_count=row.buy_count,
            hold_count=row.hold_count,
            sell_count=row.sell_count,
            target_reached_count=row.target_reached_count,
            ongoing_count=row.ongoing_count,
            stop_loss_count=row.stop_loss_count,
            latest_at=row.latest_at,
        )
        for row in rows
    ]
