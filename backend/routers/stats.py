from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Analysis
from backend.outcome import OUTCOME_STOP, OUTCOME_TARGET, TERMINAL_OUTCOMES
from backend.schemas import ModelStat, SignalCell, SignalMatrixStat

router = APIRouter(tags=["stats"])


def normalize_model(name: str) -> str:
    lower = name.lower()
    if "claude" in lower:
        return "claude"
    if "gpt" in lower or "codex" in lower:
        return "gpt"
    if "gemini" in lower or "agy" in lower:
        return "gemini"
    return lower


@router.get("/api/stats/by-model", response_model=list[ModelStat])
def get_stats_by_model(db: Session = Depends(get_db)) -> list[ModelStat]:
    analyses = db.query(Analysis).all()

    by_model: dict[str, list[Analysis]] = defaultdict(list)
    for a in analyses:
        by_model[normalize_model(a.model)].append(a)

    results = []
    for model_name, items in sorted(by_model.items()):
        total = len(items)
        judgments: dict[str, int] = defaultdict(int)
        outcomes: dict[str, int] = defaultdict(int)

        for a in items:
            judgments[a.judgment] += 1
            if a.outcome:
                outcomes[a.outcome] += 1

        win_rate = _win_rate(_buy_analyses(items))
        expectancy_pct = _expectancy(_buy_terminal(items))

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


def _win_rate(buy_analyses: list[Analysis]) -> float | None:
    if not buy_analyses:
        return None
    hits = sum(1 for a in buy_analyses if a.outcome == OUTCOME_TARGET)
    return hits / len(buy_analyses)


def _expectancy(buy_terminal: list[Analysis]) -> float | None:
    """Returns expectancy from terminal buy analyses with complete price levels."""
    hits = [a for a in buy_terminal if a.outcome == OUTCOME_TARGET]
    stops = [a for a in buy_terminal if a.outcome == OUTCOME_STOP]
    denom = len(hits) + len(stops)
    if denom == 0:
        return None
    win_rate = len(hits) / denom
    avg_gain = (
        sum((a.target_price - a.entry_price) / a.entry_price * 100 for a in hits) / len(hits)
        if hits else 0.0
    )
    avg_loss = (
        sum((a.entry_price - a.stop_loss) / a.entry_price * 100 for a in stops) / len(stops)
        if stops else 0.0
    )
    return win_rate * avg_gain - (1 - win_rate) * avg_loss


def _buy_analyses(analyses: list[Analysis]) -> list[Analysis]:
    return [a for a in analyses if a.judgment == "매수"]


def _buy_terminal(analyses: list[Analysis]) -> list[Analysis]:
    return [
        a for a in analyses
        if a.judgment == "매수"
        and a.entry_price is not None
        and a.target_price is not None
        and a.stop_loss is not None
        and a.outcome in (OUTCOME_TARGET, OUTCOME_STOP)
    ]



@router.get("/api/stats/by-signal", response_model=SignalMatrixStat)
def get_stats_by_signal(model: str, db: Session = Depends(get_db)) -> SignalMatrixStat:
    all_analyses = db.query(Analysis).all()
    analyses = [a for a in all_analyses if normalize_model(a.model) == model]
    if not analyses:
        return SignalMatrixStat(model=model, cells=[])

    grid: dict[tuple[str, str], list[Analysis]] = defaultdict(list)
    for a in analyses:
        grid[(a.cloud_position, a.ma_alignment)].append(a)

    cells: list[SignalCell] = []
    for (cloud_pos, ma_align), items in sorted(grid.items()):
        win_rate = _win_rate(_buy_analyses(items))
        expectancy_pct = _expectancy(_buy_terminal(items))
        cells.append(SignalCell(
            cloud_position=cloud_pos,
            ma_alignment=ma_align,
            count=len(items),
            win_rate=win_rate,
            expectancy_pct=expectancy_pct,
        ))

    return SignalMatrixStat(model=model, cells=cells)
