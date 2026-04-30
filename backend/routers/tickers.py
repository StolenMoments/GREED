from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.crud import search_krx_stocks
from backend.database import get_db
from backend.schemas import TickerSearchResult

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
