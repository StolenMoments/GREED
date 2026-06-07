"""KOSPI200 rule-signal backtest package."""

from .daily_rally import DAILY_RALLY_STRATEGY_KIND, run_daily_rally_backtest

__all__ = ["DAILY_RALLY_STRATEGY_KIND", "run_daily_rally_backtest"]
