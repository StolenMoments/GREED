from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.timezone import seoul_now


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=seoul_now,
        nullable=False,
    )



class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        Index("ix_analyses_run_id", "run_id"),
        Index("ix_analyses_ticker", "ticker"),
        Index("ix_analyses_judgment", "judgment"),
        Index("ix_analyses_name_initials", "name_initials"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_initials: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    judgment: Mapped[str] = mapped_column(String(20), nullable=False)
    trend: Mapped[str] = mapped_column(String(20), nullable=False)
    cloud_position: Mapped[str] = mapped_column(String(20), nullable=False)
    ma_alignment: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_price_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_price_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    outcome_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    outcome_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=seoul_now,
        nullable=False,
    )


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        Index("ix_analysis_jobs_run_id", "run_id"),
        Index("ix_analysis_jobs_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(50), default="claude", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=seoul_now,
        nullable=False,
    )


class StockPrice(Base):
    __tablename__ = "stock_prices"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    price_date: Mapped[date] = mapped_column(Date, nullable=False)
    close_price: Mapped[float] = mapped_column(Float, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FundamentalSnapshot(Base):
    __tablename__ = "fundamental_snapshots"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    per: Mapped[float | None] = mapped_column(Float, nullable=True)
    pbr: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    div_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FundamentalHistory(Base):
    __tablename__ = "fundamental_history"
    __table_args__ = (
        Index("ix_fundamental_history_lookup", "ticker", "snapshot_date"),
    )

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    per: Mapped[float | None] = mapped_column(Float, nullable=True)
    pbr: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    div_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (
        Index("ix_price_bars_lookup", "ticker", "interval", "bar_date"),
    )

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    interval: Mapped[str] = mapped_column(String(2), primary_key=True)
    bar_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    trading_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KrxStock(Base):
    __tablename__ = "krx_stocks"
    __table_args__ = (
        Index("ix_krx_stocks_name", "name"),
        Index("ix_krx_stocks_name_initials", "name_initials"),
    )

    code: Mapped[str] = mapped_column(String(6), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_initials: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=seoul_now, nullable=False)


class UsStock(Base):
    __tablename__ = "us_stocks"
    __table_args__ = (
        Index("ix_us_stocks_name", "name"),
        Index("ix_us_stocks_market", "market"),
    )

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=seoul_now, nullable=False)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=seoul_now, nullable=False
    )
    universe: Mapped[str] = mapped_column(String(50), nullable=False)
    buy_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    horizons: Mapped[str] = mapped_column(String(50), nullable=False)
    warmup_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    data_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    ticker_count: Mapped[int] = mapped_column(Integer, nullable=False)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_analysis_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strategy_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    similarity_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)


class BacktestUniverseMember(Base):
    __tablename__ = "backtest_universe_members"
    __table_args__ = (
        Index("ix_backtest_universe_members_active_order", "active", "sort_order", "ticker"),
    )

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    market: Mapped[str] = mapped_column(String(20), default="KR", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=seoul_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=seoul_now,
        onupdate=seoul_now,
        nullable=False,
    )


class BacktestPreloadJob(Base):
    __tablename__ = "backtest_preload_jobs"
    __table_args__ = (
        Index("ix_backtest_preload_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    upserted_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=seoul_now,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnalysisBacktestJob(Base):
    __tablename__ = "analysis_backtest_jobs"
    __table_args__ = (
        Index("ix_analysis_backtest_jobs_analysis_created", "analysis_id", "created_at"),
        Index("ix_analysis_backtest_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    similarity_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    backtest_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=seoul_now,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BacktestStrategyJob(Base):
    __tablename__ = "backtest_strategy_jobs"
    __table_args__ = (
        Index("ix_backtest_strategy_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    backtest_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=seoul_now,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BacktestSignal(Base):
    __tablename__ = "backtest_signals"
    __table_args__ = (
        Index("ix_backtest_signals_run", "run_id"),
        Index("ix_backtest_signals_run_bucket", "run_id", "score_bucket"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    score_bucket: Mapped[str] = mapped_column(String(10), nullable=False)
    entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    ret_4w: Mapped[float | None] = mapped_column(Float, nullable=True)
    ret_8w: Mapped[float | None] = mapped_column(Float, nullable=True)
    ret_12w: Mapped[float | None] = mapped_column(Float, nullable=True)
    ret_26w: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    days_held: Mapped[int | None] = mapped_column(Integer, nullable=True)


class BacktestStat(Base):
    __tablename__ = "backtest_stats"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    horizon: Mapped[int] = mapped_column(Integer, primary_key=True)
    score_bucket: Mapped[str] = mapped_column(String(10), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    censored_count: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    median: Mapped[float | None] = mapped_column(Float, nullable=True)
    std: Mapped[float | None] = mapped_column(Float, nullable=True)
    p25: Mapped[float | None] = mapped_column(Float, nullable=True)
    p75: Mapped[float | None] = mapped_column(Float, nullable=True)
    min: Mapped[float | None] = mapped_column(Float, nullable=True)
    max: Mapped[float | None] = mapped_column(Float, nullable=True)


class DailyRallyRuleStat(Base):
    __tablename__ = "daily_rally_rule_stats"
    __table_args__ = (
        Index("ix_daily_rally_rule_stats_run_score", "run_id", "score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_key: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_label: Mapped[str] = mapped_column(String(500), nullable=False)
    support: Mapped[int] = mapped_column(Integer, nullable=False)
    positives: Mapped[int] = mapped_column(Integer, nullable=False)
    total_matches: Mapped[int] = mapped_column(Integer, nullable=False)
    precision: Mapped[float] = mapped_column(Float, nullable=False)
    base_rate: Mapped[float] = mapped_column(Float, nullable=False)
    lift: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)


class DailyRallyPatternStat(Base):
    __tablename__ = "daily_rally_pattern_stats"
    __table_args__ = (
        Index("ix_daily_rally_pattern_stats_run_score", "run_id", "score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    pattern_key: Mapped[str] = mapped_column(String(255), nullable=False)
    pattern_label: Mapped[str] = mapped_column(String(500), nullable=False)
    support: Mapped[int] = mapped_column(Integer, nullable=False)
    positives: Mapped[int] = mapped_column(Integer, nullable=False)
    total_matches: Mapped[int] = mapped_column(Integer, nullable=False)
    precision: Mapped[float] = mapped_column(Float, nullable=False)
    base_rate: Mapped[float] = mapped_column(Float, nullable=False)
    lift: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    return_stats_json: Mapped[str] = mapped_column(Text, nullable=False)


class DailyRallyCurrentCandidate(Base):
    __tablename__ = "daily_rally_current_candidates"
    __table_args__ = (
        Index("ix_daily_rally_current_candidates_run_score", "run_id", "max_rule_score"),
        Index("ix_daily_rally_current_candidates_run_ticker", "run_id", "ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    close_price: Mapped[float] = mapped_column(Float, nullable=False)
    matched_rules_json: Mapped[str] = mapped_column(Text, nullable=False)
    matched_rule_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_rule_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_rule_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    features_json: Mapped[str] = mapped_column(Text, nullable=False)


class CandidateScanJob(Base):
    __tablename__ = "candidate_scan_jobs"
    __table_args__ = (
        Index("ix_candidate_scan_jobs_status_created", "status", "created_at"),
        Index("ix_candidate_scan_jobs_analysis_created", "analysis_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    candidate_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scan_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=seoul_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CurrentCandidate(Base):
    __tablename__ = "current_candidates"
    __table_args__ = (
        Index("ix_current_candidates_lookup", "analysis_id", "scan_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(Integer, nullable=False)
    scan_date: Mapped[date] = mapped_column(Date, nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    current_close: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_price: Mapped[float] = mapped_column(Float, nullable=False)
    entry_gap_pct: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=seoul_now, nullable=False
    )
