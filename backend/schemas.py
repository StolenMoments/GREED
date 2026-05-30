from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JudgmentEnum(str, Enum):
    buy = "매수"
    hold = "홀드"
    sell = "매도"


class OutcomeEnum(str, Enum):
    target_reached = "목표달성"
    stop_loss = "손절"
    ongoing = "진행중"
    na = "판정불가"


class EntryCandidateFilterEnum(str, Enum):
    all = "all"
    pullback = "pullback"
    breakout = "breakout"


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
    target_price: float | None = None
    target_price_max: float | None = None
    stop_loss: float | None = None
    stop_loss_max: float | None = None
    current_price: float | None = None
    current_price_date: date | None = None
    entry_gap_pct: float | None = None
    is_entry_near: bool = False
    entry_candidates: list[EntryCandidateSummary] = Field(default_factory=list)
    outcome: str | None = None
    outcome_date: date | None = None
    outcome_price: float | None = None


class AnalysisPage(BaseModel):
    items: list[AnalysisSummary]
    page: int
    page_size: int
    total: int
    total_pages: int


class AnalysisRead(AnalysisSummary):
    markdown: str


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


class JobOverviewRead(BaseModel):
    kind: Literal["analysis", "analysis_backtest"]
    id: int
    ticker: str
    run_id: int
    model: str
    status: str
    error_message: str | None
    analysis_id: int | None
    backtest_run_id: int | None = None
    similarity_threshold: int | None = None
    created_at: datetime


class EvaluateOutcomesResult(BaseModel):
    evaluated: int
    skipped: int


class AnalysisBacktestJobCreate(BaseModel):
    pass


class AnalysisBacktestJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    analysis_id: int
    status: str
    similarity_threshold: int
    backtest_run_id: int | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class StockPriceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    price_date: date
    close_price: float
    fetched_at: datetime


class StockSummaryRead(BaseModel):
    ticker: str
    name: str
    name_initials: str
    buy_count: int
    hold_count: int
    sell_count: int
    target_reached_count: int
    ongoing_count: int
    stop_loss_count: int
    latest_at: datetime


class TickerSearchResult(BaseModel):
    code: str
    name: str
    market: Literal["KR", "US"] = "KR"


class ModelStat(BaseModel):
    model: str
    total: int
    judgments: dict[str, int]
    outcomes: dict[str, int]
    win_rate: float | None
    expectancy_pct: float | None
    avg_holding_weeks: float | None



class SignalCell(BaseModel):
    cloud_position: str
    ma_alignment: str
    count: int
    win_rate: float | None
    expectancy_pct: float | None


class SignalMatrixStat(BaseModel):
    model: str
    cells: list[SignalCell]


class BacktestStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    horizon: int
    score_bucket: str
    count: int
    censored_count: int
    win_rate: float | None
    mean: float | None
    median: float | None
    std: float | None
    p25: float | None
    p75: float | None
    min: float | None
    max: float | None


class BacktestEventSummary(BaseModel):
    signal_count: int
    entered_count: int
    no_entry_count: int
    target_count: int
    stop_count: int
    expiry_count: int
    target_hit_rate: float | None
    positive_return_rate: float | None
    win_rate: float | None
    mean_return: float | None
    median_return: float | None
    avg_days_held: float | None


class BacktestRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    universe: str
    buy_threshold: int
    horizons: str
    warmup_weeks: int
    data_start: date | None
    data_end: date | None
    ticker_count: int
    signal_count: int
    notes: str | None
    source_analysis_id: int | None = None
    strategy_kind: str | None = None
    similarity_threshold: int | None = None
    source_ticker: str | None = None
    source_name: str | None = None


class BacktestRunDetail(BacktestRunSummary):
    stats: list[BacktestStatRead]
    event_summary: BacktestEventSummary | None = None


class BacktestSignalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    name: str
    signal_date: date
    score: int
    score_bucket: str
    entry_date: date | None
    entry_price: float
    ret_4w: float | None
    ret_8w: float | None
    ret_12w: float | None
    ret_26w: float | None
    exit_date: date | None = None
    exit_reason: str | None = None
    exit_price: float | None = None
    event_return: float | None = None
    days_held: int | None = None


class BacktestSignalPage(BaseModel):
    total: int
    items: list[BacktestSignalRead]


class HistogramBin(BaseModel):
    lower: float
    upper: float
    count: int


class BacktestHistogram(BaseModel):
    horizon: int
    score_bucket: str
    bins: list[HistogramBin]


class BacktestUniverseMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    name: str
    market: str
    active: bool
    sort_order: int
    source: str
    created_at: datetime
    updated_at: datetime


class BacktestUniverseMemberCreate(BaseModel):
    ticker: str = Field(..., max_length=20)
    name: str = Field(..., max_length=255)
    market: Literal["KR"] = "KR"
    active: bool = True
    sort_order: int = 0
    source: str = Field(default="manual", max_length=50)


class BacktestUniverseMemberUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    active: bool | None = None
    sort_order: int | None = None
