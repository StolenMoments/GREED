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
    kind: Literal["analysis", "analysis_backtest", "backtest_preload", "backtest_strategy", "candidate_scan"]
    id: int
    ticker: str
    run_id: int | None
    model: str
    status: str
    error_message: str | None
    analysis_id: int | None
    backtest_run_id: int | None = None
    similarity_threshold: int | None = None
    upserted_rows: int | None = None
    created_at: datetime


class EvaluateOutcomesResult(BaseModel):
    evaluated: int
    skipped: int


class AnalysisBacktestJobCreate(BaseModel):
    similarity_threshold: Literal[10, 11, 12] = 12


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


class BacktestStrategyJobCreate(BaseModel):
    strategy_kind: Literal["ichimoku_span2_breakout", "daily_20d_40pct_rally"]


class BacktestStrategyJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_kind: str
    status: str
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


class DailyRallyRuleStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    rule_key: str
    rule_label: str
    support: int
    positives: int
    total_matches: int
    precision: float
    base_rate: float
    lift: float
    score: float


class DailyRallyInsightsRead(BaseModel):
    run_id: int
    rule_count: int
    rules: list[DailyRallyRuleStatRead]


class DailyRallyReturnStatRead(BaseModel):
    horizon: int
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


class DailyRallyPatternStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    pattern_key: str
    pattern_label: str
    support: int
    positives: int
    total_matches: int
    precision: float
    base_rate: float
    lift: float
    score: float
    return_stats: list[DailyRallyReturnStatRead]


class DailyRallyPatternStatsRead(BaseModel):
    run_id: int
    pattern_count: int
    patterns: list[DailyRallyPatternStatRead]


class DailyRallyRuleScoreBreakdownRead(BaseModel):
    rule_key: str
    rule_label: str
    rule_composite: float
    rule_quality: float
    stability_multiplier: float
    stability_classification: str
    expected_return: float
    win_rate_20d: float | None = None
    median_return_20d: float | None = None


class DailyRallyCandidateRead(BaseModel):
    id: int
    run_id: int
    ticker: str
    name: str
    signal_date: date
    close_price: float
    matched_rules: list[str]
    matched_rule_count: int
    max_rule_score: float | None
    mean_rule_score: float | None
    features: dict[str, bool | int | float | str | None]
    composite_score: float | None = None
    best_rule_key: str | None = None
    rule_quality_score: float | None = None
    stability_score: float | None = None
    stability_classification: str | None = None
    expected_return_score: float | None = None
    expected_win_rate_20d: float | None = None
    expected_median_return_20d: float | None = None
    rule_breakdowns: list[DailyRallyRuleScoreBreakdownRead] = []


class DailyRallyCandidatesRead(BaseModel):
    run_id: int
    candidate_count: int
    candidates: list[DailyRallyCandidateRead]


class DailyRallyYearValidationRead(BaseModel):
    year: int
    total: int
    positives: int
    base_rate: float
    positive_forward_return_120d_mean: float | None
    censored_120d_count: int
    partial: bool


class DailyRallyTickerConcentrationRead(BaseModel):
    ticker: str
    name: str
    total_count: int
    positive_count: int
    positive_share: float


class DailyRallyPatternStabilityRead(BaseModel):
    pattern_key: str
    pattern_label: str
    total_matches: int
    positives: int
    full_period_lift: float
    test_window_count: int
    median_train_lift: float | None
    median_test_lift: float | None
    test_lift_gt_1_ratio: float | None
    classification: Literal["stable", "fragile", "insufficient"]


class DailyRallyWalkForwardWindowRead(BaseModel):
    train_years: list[int]
    test_year: int
    pattern_key: str | None
    pattern_label: str | None
    train_support: int
    train_total_matches: int
    train_precision: float | None
    train_base_rate: float | None
    train_lift: float | None
    test_matches: int
    test_positives: int
    test_precision: float | None
    test_base_rate: float | None
    test_lift: float | None
    classification: Literal["stable", "fragile", "insufficient"]


class DailyRallyValidationRead(BaseModel):
    run_id: int
    summary: dict[str, object]
    year_breakdown: list[DailyRallyYearValidationRead]
    ticker_concentration: list[DailyRallyTickerConcentrationRead]
    pattern_stability: list[DailyRallyPatternStabilityRead]
    walk_forward_windows: list[DailyRallyWalkForwardWindowRead]
    warnings: list[str]


class BacktestEventSummary(BaseModel):
    signal_count: int
    entered_count: int
    no_entry_count: int
    target_count: int
    stop_count: int
    open_count: int = 0
    expiry_count: int
    target_hit_rate: float | None
    positive_return_rate: float | None
    win_rate: float | None
    mean_return: float | None
    expectancy: float | None
    median_return: float | None
    avg_days_held: float | None
    planned_target_return: float | None = None
    planned_stop_return: float | None = None
    planned_risk_reward_ratio: float | None = None
    avg_gain_return: float | None = None
    avg_loss_return: float | None = None
    realized_payoff_ratio: float | None = None


class ContractBreakdownItem(BaseModel):
    signal_count: int
    entered_count: int
    no_entry_count: int
    target_count: int
    stop_count: int
    expiry_count: int
    target_hit_rate: float | None
    positive_return_rate: float | None
    mean_return: float | None
    median_return: float | None
    avg_days_held: float | None


class ContractTickerBreakdownItem(ContractBreakdownItem):
    ticker: str
    name: str


class ContractBreakdown(BaseModel):
    focus_threshold: int
    focus: ContractBreakdownItem
    by_score: dict[str, ContractBreakdownItem]
    by_year: dict[str, ContractBreakdownItem]
    top_tickers: list[ContractTickerBreakdownItem]
    bottom_tickers: list[ContractTickerBreakdownItem]


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
    contract_breakdown: ContractBreakdown | None = None


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


class CandidateRead(BaseModel):
    id: int
    analysis_id: int
    scan_date: date
    ticker: str
    name: str
    score: int
    current_close: float
    entry_price: float
    target_price: float
    stop_price: float
    entry_gap_pct: float

    model_config = ConfigDict(from_attributes=True)


class ScanSummaryItem(BaseModel):
    analysis_id: int
    ticker: str
    name: str
    latest_scan_date: date | None
    threshold: int | None
    candidate_count: int | None
    status: str
    latest_job_id: int | None


class CandidateScanJobCreate(BaseModel):
    threshold: int = 12


class CandidateScanJobRead(BaseModel):
    id: int
    analysis_id: int
    threshold: int
    status: str
    candidate_count: int | None
    scan_date: date | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
