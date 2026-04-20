from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.crud import create_run, get_run, get_runs
from backend.database import get_db
from backend.schemas import RunCreate, RunRead


router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=RunRead, status_code=status.HTTP_201_CREATED)
def create_run_endpoint(
    payload: RunCreate,
    db: Session = Depends(get_db),
) -> RunRead:
    return create_run(db, memo=payload.memo)


@router.get("", response_model=list[RunRead])
def list_runs_endpoint(db: Session = Depends(get_db)) -> list[RunRead]:
    return get_runs(db)


@router.get("/{run_id}", response_model=RunRead)
def get_run_endpoint(run_id: int, db: Session = Depends(get_db)) -> RunRead:
    run = get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run
