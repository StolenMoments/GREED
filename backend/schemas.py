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
    target_price: float | None = None
    stop_loss: float | None = None


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


class StockPriceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    price_date: date
    close_price: float
    fetched_at: datetime
