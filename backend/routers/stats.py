from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Analysis
from backend.outcome import OUTCOME_STOP, OUTCOME_TARGET, TERMINAL_OUTCOMES
from backend.schemas import HeadToHeadModelRow, HeadToHeadStat, ModelStat, SignalCell, SignalMatrixStat

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


def _expectancy(buy_terminal: list[Analysis]) -> tuple[float | None, float | None]:
    """Returns (win_rate, expectancy_pct) from a list of terminal buy analyses."""
    hits = [a for a in buy_terminal if a.outcome == OUTCOME_TARGET]
    stops = [a for a in buy_terminal if a.outcome == OUTCOME_STOP]
    denom = len(hits) + len(stops)
    if denom == 0:
        return None, None
    win_rate = len(hits) / denom
    avg_gain = (
        sum((a.target_price - a.entry_price) / a.entry_price * 100 for a in hits) / len(hits)
        if hits else 0.0
    )
    avg_loss = (
        sum((a.entry_price - a.stop_loss) / a.entry_price * 100 for a in stops) / len(stops)
        if stops else 0.0
    )
    return win_rate, win_rate * avg_gain - (1 - win_rate) * avg_loss


def _buy_terminal(analyses: list[Analysis]) -> list[Analysis]:
    return [
        a for a in analyses
        if a.judgment == "매수"
        and a.entry_price is not None
        and a.target_price is not None
        and a.stop_loss is not None
        and a.outcome in (OUTCOME_TARGET, OUTCOME_STOP)
    ]


@router.get("/api/stats/head-to-head", response_model=HeadToHeadStat)
def get_head_to_head(run_id: int | None = None, db: Session = Depends(get_db)) -> HeadToHeadStat:
    _empty = HeadToHeadStat(run_id=run_id, tickers=0, matrix=[], agreement={})
    if run_id is None:
        return _empty

    analyses = db.query(Analysis).filter(Analysis.run_id == run_id).all()
    if not analyses:
        return _empty

    # Group by model → ticker → analysis
    by_model: dict[str, dict[str, Analysis]] = defaultdict(dict)
    for a in analyses:
        by_model[a.model][a.ticker] = a

    if not by_model:
        return _empty

    # Intersection of tickers across all models
    ticker_sets = [set(td.keys()) for td in by_model.values()]
    common_tickers: set[str] = ticker_sets[0].intersection(*ticker_sets[1:])

    # Matrix: per-model stats on common tickers only
    matrix: list[HeadToHeadModelRow] = []
    for model_name in sorted(by_model.keys()):
        items = [by_model[model_name][t] for t in common_tickers if t in by_model[model_name]]
        buy_items = [a for a in items if a.judgment == "매수"]
        terminal = _buy_terminal(buy_items)
        hits = sum(1 for a in terminal if a.outcome == OUTCOME_TARGET)
        stops = sum(1 for a in terminal if a.outcome == OUTCOME_STOP)
        _, expectancy_pct = _expectancy(terminal)
        matrix.append(HeadToHeadModelRow(
            model=model_name,
            buy=len(buy_items),
            hits=hits,
            stops=stops,
            expectancy_pct=expectancy_pct,
        ))

    # Agreement: per-ticker, which models flagged as 매수
    all_tickers: set[str] = set()
    for td in by_model.values():
        all_tickers.update(td.keys())

    agreement: dict[str, int] = defaultdict(int)
    for ticker in all_tickers:
        buy_models = sorted(
            m for m, td in by_model.items()
            if td.get(ticker) is not None and td[ticker].judgment == "매수"
        )
        if not buy_models:
            continue
        key = "_and_".join(buy_models) if len(buy_models) > 1 else f"{buy_models[0]}_only"
        agreement[key] += 1

    return HeadToHeadStat(
        run_id=run_id,
        tickers=len(common_tickers),
        matrix=matrix,
        agreement=dict(agreement),
    )


@router.get("/api/stats/by-signal", response_model=SignalMatrixStat)
def get_stats_by_signal(model: str, db: Session = Depends(get_db)) -> SignalMatrixStat:
    analyses = db.query(Analysis).filter(Analysis.model == model).all()
    if not analyses:
        return SignalMatrixStat(model=model, cells=[])

    grid: dict[tuple[str, str], list[Analysis]] = defaultdict(list)
    for a in analyses:
        grid[(a.cloud_position, a.ma_alignment)].append(a)

    cells: list[SignalCell] = []
    for (cloud_pos, ma_align), items in sorted(grid.items()):
        terminal = _buy_terminal(items)
        win_rate, expectancy_pct = _expectancy(terminal)
        cells.append(SignalCell(
            cloud_position=cloud_pos,
            ma_alignment=ma_align,
            count=len(items),
            win_rate=win_rate,
            expectancy_pct=expectancy_pct,
        ))

    return SignalMatrixStat(model=model, cells=cells)
