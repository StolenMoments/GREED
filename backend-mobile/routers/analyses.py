from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import crud
from auth import verify_api_key
from database import get_db
from schemas import AnalysesPage, AnalysisDetail

_Judgment = Literal["매수", "홀드", "매도"]

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.get("", response_model=AnalysesPage, dependencies=[Depends(verify_api_key)])
def get_analyses(
    judgment: _Judgment | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> AnalysesPage:
    return crud.list_analyses(db, judgment=judgment, q=q, page=page, per_page=per_page)


@router.get("/{analysis_id}", response_model=AnalysisDetail, dependencies=[Depends(verify_api_key)])
def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
) -> AnalysisDetail:
    analysis = crud.get_analysis(db, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return AnalysisDetail.model_validate(analysis)
