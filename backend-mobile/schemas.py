from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AnalysisItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: str
    judgment: str
    trend: str
    cloud_position: str
    ma_alignment: str
    created_at: datetime


class AnalysisDetail(AnalysisItem):
    markdown: str


class AnalysesPage(BaseModel):
    items: list[AnalysisItem]
    page: int
    per_page: int
    total: int
    total_pages: int


class StockSummary(BaseModel):
    ticker: str
    name: str
    buy_count: int
    hold_count: int
    sell_count: int
    latest_at: datetime
