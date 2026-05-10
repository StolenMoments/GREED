from __future__ import annotations

from datetime import date, datetime

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
    entry_price: float | None = None
    entry_price_max: float | None = None
    target_price: float | None = None
    target_price_max: float | None = None
    stop_loss: float | None = None
    stop_loss_max: float | None = None
    current_price: float | None = None
    current_price_date: date | None = None


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
