from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.crud import (
    create_analysis,
    get_analyses,
    get_analyses_by_run,
    get_analyses_page,
    get_analysis,
    get_analysis_history,
    get_run,
    get_stock_price,
    upsert_stock_price,
)
from backend.database import get_db
from backend.parser import parse_markdown
from backend.schemas import AnalysisCreate, AnalysisPage, AnalysisRead, AnalysisSummary, JudgmentEnum
from backend.stock_price import fetch_latest_close


router = APIRouter(tags=["analyses"])


@router.post("/api/analyses", response_model=AnalysisRead, status_code=status.HTTP_201_CREATED)
def create_analysis_endpoint(
    payload: AnalysisCreate,
    db: Session = Depends(get_db),
) -> AnalysisRead | Response:
    if get_run(db, payload.run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    parse_result = parse_markdown(payload.markdown)
    if not parse_result.success:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "파싱 실패", "failed_fields": parse_result.failed},
        )

    analysis_payload = payload.model_copy(update=parse_result.data)
    return create_analysis(db, analysis_payload)


@router.get("/api/analyses", response_model=AnalysisPage)
def list_analyses_endpoint(
    judgment: JudgmentEnum | None = None,
    run_id: int | None = None,
    q: str | None = None,
    entry_gap_lte: float | None = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> AnalysisPage:
    judgment_value = judgment.value if judgment else None
    if entry_gap_lte is not None:
        _refresh_candidate_stock_prices(db, judgment=judgment_value, run_id=run_id, q=q)

    return AnalysisPage(
        **get_analyses_page(
            db,
            judgment=judgment_value,
            run_id=run_id,
            q=q,
            entry_gap_lte=entry_gap_lte,
            page=page,
            page_size=page_size,
        )._asdict()
    )


@router.get("/api/runs/{run_id}/analyses", response_model=list[AnalysisSummary])
def list_analyses_by_run_endpoint(
    run_id: int,
    judgment: JudgmentEnum | None = None,
    db: Session = Depends(get_db),
) -> list[AnalysisSummary]:
    if get_run(db, run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return get_analyses_by_run(db, run_id, judgment=judgment.value if judgment else None)


@router.get("/api/analyses/{analysis_id}", response_model=AnalysisRead)
def get_analysis_endpoint(
    analysis_id: int,
    db: Session = Depends(get_db),
) -> AnalysisRead:
    analysis = get_analysis(db, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return analysis


@router.get("/api/analyses/{analysis_id}/history", response_model=list[AnalysisSummary])
def get_analysis_history_endpoint(
    analysis_id: int,
    db: Session = Depends(get_db),
) -> list[AnalysisSummary]:
    analysis = get_analysis(db, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return get_analysis_history(db, analysis.ticker)


def _refresh_candidate_stock_prices(
    db: Session,
    judgment: str | None,
    run_id: int | None,
    q: str | None,
) -> None:
    tickers = {
        analysis.ticker
        for analysis in get_analyses(db, judgment=judgment, run_id=run_id, q=q)
        if analysis.entry_price is not None
    }

    for ticker in tickers:
        cached = get_stock_price(db, ticker)
        if cached is not None and cached.price_date >= date.today():
            continue

        try:
            result = fetch_latest_close(ticker)
        except Exception:
            continue

        if result is None:
            continue

        price_date, close_price = result
        upsert_stock_price(db, ticker=ticker, price_date=price_date, close_price=close_price)
