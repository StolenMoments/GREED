from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import crud
from auth import verify_api_key
from database import get_db
from schemas import StockSummary


router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/summary", response_model=list[StockSummary], dependencies=[Depends(verify_api_key)])
def get_stocks_summary(db: Session = Depends(get_db)) -> list[StockSummary]:
    return crud.list_stock_summary(db)
