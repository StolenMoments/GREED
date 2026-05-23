from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Analysis
from backend.outcome import OUTCOME_STOP, OUTCOME_TARGET, TERMINAL_OUTCOMES
from backend.schemas import ModelStat

router = APIRouter(tags=["stats"])


@router.get("/api/stats/by-model", response_model=list[ModelStat])
def get_stats_by_model(db: Session = Depends(get_db)) -> list[ModelStat]:
    analyses = db.query(Analysis).all()

    by_model: dict[str, list[Analysis]] = defaultdict(list)
    for a in analyses:
        by_model[a.model].append(a)

    results = []
    for model_name, items in sorted(by_model.items()):
        total = len(items)
        judgments: dict[str, int] = defaultdict(int)
        outcomes: dict[str, int] = defaultdict(int)

        for a in items:
            judgments[a.judgment] += 1
            if a.outcome:
                outcomes[a.outcome] += 1

        # win_rate & expectancy: 매수 only, entry/target/stop all non-null, terminal outcome
        buy_terminal = [
            a for a in items
            if a.judgment == "매수"
            and a.entry_price is not None
            and a.target_price is not None
            and a.stop_loss is not None
            and a.outcome in (OUTCOME_TARGET, OUTCOME_STOP)
        ]

        win_count = sum(1 for a in buy_terminal if a.outcome == OUTCOME_TARGET)
        loss_count = sum(1 for a in buy_terminal if a.outcome == OUTCOME_STOP)
        denom = win_count + loss_count

        win_rate = win_count / denom if denom > 0 else None

        if win_rate is not None:
            wins = [a for a in buy_terminal if a.outcome == OUTCOME_TARGET]
            losses = [a for a in buy_terminal if a.outcome == OUTCOME_STOP]

            avg_gain = (
                sum((a.target_price - a.entry_price) / a.entry_price * 100 for a in wins) / len(wins)
                if wins else 0.0
            )
            avg_loss = (
                sum((a.entry_price - a.stop_loss) / a.entry_price * 100 for a in losses) / len(losses)
                if losses else 0.0
            )
            expectancy_pct = win_rate * avg_gain - (1 - win_rate) * avg_loss
        else:
            expectancy_pct = None

        # avg_holding_weeks: terminal outcomes with outcome_date set
        terminated = [
            a for a in items
            if a.outcome_date is not None and a.outcome in TERMINAL_OUTCOMES
        ]

        if terminated:
            holding_days = [
                (a.outcome_date - a.created_at.date()).days
                for a in terminated
            ]
            avg_holding_weeks = sum(holding_days) / len(holding_days) / 7
        else:
            avg_holding_weeks = None

        results.append(ModelStat(
            model=model_name,
            total=total,
            judgments=dict(judgments),
            outcomes=dict(outcomes),
            win_rate=win_rate,
            expectancy_pct=expectancy_pct,
            avg_holding_weeks=avg_holding_weeks,
        ))

    return results
