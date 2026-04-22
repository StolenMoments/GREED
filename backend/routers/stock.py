from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend import crud
from backend.database import get_db
from backend.schemas import StockPriceRead
from backend.stock_price import fetch_latest_close
from backend.tickers import normalize_ticker

router = APIRouter(prefix="/api/stock", tags=["stock"])


@router.get("/{ticker}/price", response_model=StockPriceRead)
def get_stock_price(ticker: str, db: Session = Depends(get_db)) -> StockPriceRead:
    ticker = normalize_ticker(ticker)
    cached = crud.get_stock_price(db, ticker)
    if cached is not None and cached.price_date >= date.today():
        return cached  # type: ignore[return-value]

    result = fetch_latest_close(ticker)
    if result is None:
        raise HTTPException(status_code=404, detail="가격 데이터를 가져올 수 없습니다.")

    price_date, close_price = result
    return crud.upsert_stock_price(db, ticker, price_date, close_price)  # type: ignore[return-value]
