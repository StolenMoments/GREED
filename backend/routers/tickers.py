from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.crud import get_krx_stock_by_code, search_krx_stocks
from backend.database import get_db
from backend.schemas import TickerSearchResult
from backend.tickers import normalize_ticker

router = APIRouter(prefix="/api/tickers", tags=["tickers"])


def _is_korean(text: str) -> bool:
    return any('가' <= c <= '힣' or 'ㄱ' <= c <= 'ㅎ' for c in text)


@router.get("/search", response_model=list[TickerSearchResult])
def search_tickers(
    q: str = Query(..., min_length=1, max_length=50),
    db: Session = Depends(get_db),
) -> list[TickerSearchResult]:
    q = q.strip()
    if not _is_korean(q):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Korean query required")
    results = search_krx_stocks(db, q)
    return [TickerSearchResult(code=r.code, name=r.name) for r in results]


@router.get("/{code}", response_model=TickerSearchResult)
def get_ticker(
    code: str,
    db: Session = Depends(get_db),
) -> TickerSearchResult:
    normalized = normalize_ticker(code)
    if not normalized.isdigit() or len(normalized) != 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="6-digit Korean ticker required")

    result = get_krx_stock_by_code(db, normalized)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticker not found")

    return TickerSearchResult(code=result.code, name=result.name)
