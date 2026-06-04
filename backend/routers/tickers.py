from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.crud import get_krx_stock_by_code, get_us_stock_by_code, search_krx_stocks, search_us_stocks
from backend.database import get_db
from backend.schemas import TickerSearchResult
from backend.tickers import is_potential_krx_ticker, normalize_ticker

router = APIRouter(prefix="/api/tickers", tags=["tickers"])


@router.get("/search", response_model=list[TickerSearchResult])
def search_tickers(
    q: str = Query(..., min_length=1, max_length=50),
    db: Session = Depends(get_db),
) -> list[TickerSearchResult]:
    q = q.strip()
    kr_results = [
        TickerSearchResult(code=r.code, name=r.name, market="KR")
        for r in search_krx_stocks(db, q)
    ]
    us_results = [
        TickerSearchResult(code=r.code, name=r.name, market="US")
        for r in search_us_stocks(db, q)
    ]
    return (kr_results + us_results)[:10]


@router.get("/{code}", response_model=TickerSearchResult)
def get_ticker(
    code: str,
    db: Session = Depends(get_db),
) -> TickerSearchResult:
    normalized = normalize_ticker(code)
    if not normalized.isalnum():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ticker code")

    if normalized.isdigit() and len(normalized) != 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="6-digit Korean ticker required")

    if is_potential_krx_ticker(normalized):
        result = get_krx_stock_by_code(db, normalized)
        if result is not None:
            return TickerSearchResult(code=result.code, name=result.name, market="KR")

    us_result = get_us_stock_by_code(db, normalized)
    if us_result is not None:
        return TickerSearchResult(code=us_result.code, name=us_result.name, market="US")

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticker not found")
