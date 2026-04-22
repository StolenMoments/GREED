from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class JudgmentEnum(str, Enum):
    buy = "매수"
    hold = "홀드"
    sell = "매도"


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
    ticker: str = Field(..., max_length=20)
    name: str = Field(..., max_length=100)
    model: str = Field(..., max_length=100)
    markdown: str
    judgment: str
    trend: str
    cloud_position: str
    ma_alignment: str
    entry_price: float | None = None
    entry_price_max: float | None = None
    target_price: float | None = None
    target_price_max: float | None = None
    stop_loss: float | None = None
    stop_loss_max: float | None = None


class EntryCandidateSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    price: float
    price_max: float | None = None
    gap_pct: float | None = None
    is_near: bool = False


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
    entry_price: float | None = None
    entry_price_max: float | None = None
    current_price: float | None = None
    current_price_date: date | None = None
    entry_gap_pct: float | None = None
    is_entry_near: bool = False
    entry_candidates: list[EntryCandidateSummary] = Field(default_factory=list)


class AnalysisPage(BaseModel):
    items: list[AnalysisSummary]
    page: int
    page_size: int
    total: int
    total_pages: int


class AnalysisRead(AnalysisSummary):
    markdown: str
    target_price: float | None
    target_price_max: float | None
    stop_loss: float | None
    stop_loss_max: float | None


class JobTriggerRequest(BaseModel):
    ticker: str = Field(..., max_length=20)
    run_id: int
    model: str = Field(default="claude", max_length=50)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    run_id: int
    model: str
    status: str
    error_message: str | None
    raw_markdown: str | None
    analysis_id: int | None
    created_at: datetime


class StockPriceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    price_date: date
    close_price: float
    fetched_at: datetime
