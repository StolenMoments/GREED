from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models import (  # noqa: E402
    BacktestRun,
    BacktestSignal,
    BacktestStat,
    DailyRallyCurrentCandidate,
    DailyRallyRuleStat,
)

from .daily_rally import DAILY_RALLY_STRATEGY_KIND, DailyRallyBacktestResult  # noqa: E402
from .engine import HORIZONS, SignalRecord, StatRow, aggregate  # noqa: E402


_DAILY_RALLY_HORIZON_MAP = {
    4: 20,
    8: 40,
    12: 60,
    26: 120,
}


def persist_run(
    db: Session,
    *,
    buy_threshold: int,
    warmup_weeks: int,
    ticker_count: int,
    records: list[SignalRecord],
    stats: list[StatRow],
    data_start: date | None,
    data_end: date | None,
    notes: str | None = None,
    source_analysis_id: int | None = None,
    strategy_kind: str | None = None,
    similarity_threshold: int | None = None,
    horizons: str | None = None,
    universe: str = "KOSPI200-DB",
    commit: bool = True,
) -> int:
    run = BacktestRun(
        universe=universe,
        buy_threshold=buy_threshold,
        horizons=horizons or ",".join(str(h) for h in HORIZONS),
        warmup_weeks=warmup_weeks,
        data_start=data_start,
        data_end=data_end,
        ticker_count=ticker_count,
        signal_count=len(records),
        notes=notes,
        source_analysis_id=source_analysis_id,
        strategy_kind=strategy_kind,
        similarity_threshold=similarity_threshold,
    )
    db.add(run)
    db.flush()  # run.id 확보

    for r in records:
        db.add(
            BacktestSignal(
                run_id=run.id,
                ticker=r.ticker,
                name=r.name,
                signal_date=r.signal_date,
                score=r.score,
                score_bucket=r.score_bucket,
                entry_date=r.entry_date,
                entry_price=r.entry_price,
                ret_4w=r.returns.get(4),
                ret_8w=r.returns.get(8),
                ret_12w=r.returns.get(12),
                ret_26w=r.returns.get(26),
                exit_date=r.exit_date,
                exit_reason=r.exit_reason,
                exit_price=r.exit_price,
                event_return=r.event_return,
                days_held=r.days_held,
            )
        )
    for s in stats:
        db.add(
            BacktestStat(
                run_id=run.id,
                horizon=s.horizon,
                score_bucket=s.score_bucket,
                count=s.count,
                censored_count=s.censored_count,
                win_rate=s.win_rate,
                mean=s.mean,
                median=s.median,
                std=s.std,
                p25=s.p25,
                p75=s.p75,
                min=s.min,
                max=s.max,
            )
        )
    if commit:
        db.commit()
    return run.id


def persist_daily_rally_run(db: Session, result: DailyRallyBacktestResult) -> int:
    records = [_daily_rally_sample_to_signal_record(sample) for sample in result.samples]
    stats = aggregate(
        records,
        horizons=(20, 40, 60, 120),
        buckets=("positive", "control", "ALL"),
    )
    run_id = persist_run(
        db,
        buy_threshold=0,
        warmup_weeks=0,
        ticker_count=result.ticker_count,
        records=records,
        stats=stats,
        data_start=result.data_start,
        data_end=result.data_end,
        notes="daily 20 trading day +40% rally rule mining",
        strategy_kind=DAILY_RALLY_STRATEGY_KIND,
        horizons="20d,40d,60d,120d",
        universe="KOSPI200-DB",
        commit=False,
    )

    for rule in result.rules:
        db.add(
            DailyRallyRuleStat(
                run_id=run_id,
                rule_key=rule.rule_key,
                rule_label=rule.rule_label,
                support=rule.support,
                positives=rule.positives,
                total_matches=rule.total_matches,
                precision=rule.precision,
                base_rate=rule.base_rate,
                lift=rule.lift,
                score=rule.score,
            )
        )

    for candidate in result.current_candidates:
        db.add(
            DailyRallyCurrentCandidate(
                run_id=run_id,
                ticker=candidate.ticker,
                name=candidate.name,
                signal_date=candidate.signal_date,
                close_price=candidate.close_price,
                matched_rules_json=json.dumps(
                    candidate.matched_rules,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                matched_rule_count=candidate.matched_rule_count,
                max_rule_score=candidate.max_rule_score,
                mean_rule_score=candidate.mean_rule_score,
                features_json=json.dumps(
                    candidate.features,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        )

    db.commit()
    return run_id


def _daily_rally_sample_to_signal_record(sample) -> SignalRecord:
    returns = {
        storage_horizon: sample.forward_returns.get(daily_horizon)
        for storage_horizon, daily_horizon in _DAILY_RALLY_HORIZON_MAP.items()
    }
    returns.update(
        {
            daily_horizon: sample.forward_returns.get(daily_horizon)
            for daily_horizon in _DAILY_RALLY_HORIZON_MAP.values()
        }
    )
    return SignalRecord(
        ticker=sample.ticker,
        name=sample.name,
        signal_date=sample.signal_date,
        score=int(sample.label),
        score_bucket="positive" if sample.label else "control",
        entry_date=sample.signal_date,
        entry_price=sample.close_price,
        returns=returns,
    )
