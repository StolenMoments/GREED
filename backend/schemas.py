from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RunCreate(BaseModel):
    memo: str | None = None


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    memo: str | None
    created_at: datetime
    analysis_count: int


class AnalysisCreate(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: int
    ticker: str
    name: str
    model: str
    markdown: str


class AnalysisSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    ticker: str
    name: str
    model: str
    judgment: str
    trend: str
    cloud_position: str
    ma_alignment: str
    created_at: datetime


class AnalysisRead(AnalysisSummary):
    markdown: str
    entry_price: float | None
    target_price: float | None
    stop_loss: float | None
