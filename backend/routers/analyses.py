from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.crud import create_analysis, get_analyses_by_run, get_analysis, get_analysis_history
from backend.database import get_db
from backend.parser import parse_markdown
from backend.schemas import AnalysisCreate, AnalysisRead, AnalysisSummary


router = APIRouter(tags=["analyses"])


@router.post("/api/analyses", response_model=AnalysisRead, status_code=status.HTTP_201_CREATED)
def create_analysis_endpoint(
    payload: AnalysisCreate,
    db: Session = Depends(get_db),
) -> AnalysisRead:
    parse_result = parse_markdown(payload.markdown)
    if not parse_result.success:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"detail": "파싱 실패", "failed_fields": parse_result.failed},
        )

    analysis_payload = payload.model_copy(update=parse_result.data)
    return create_analysis(db, analysis_payload)


@router.get("/api/runs/{run_id}/analyses", response_model=list[AnalysisSummary])
def list_analyses_by_run_endpoint(
    run_id: int,
    judgment: str | None = None,
    db: Session = Depends(get_db),
) -> list[AnalysisSummary]:
    return get_analyses_by_run(db, run_id, judgment=judgment)


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
