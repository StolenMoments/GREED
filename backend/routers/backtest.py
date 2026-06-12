from __future__ import annotations

import json

import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database import SessionLocal, get_db
from backend.models import (
    Analysis,
    BacktestPreloadJob,
    BacktestRun,
    BacktestSignal,
    BacktestStat,
    BacktestStrategyJob,
    BacktestUniverseMember,
    DailyRallyCurrentCandidate,
    DailyRallyPatternStat,
    DailyRallyRuleStat,
    DailyRallyValidationSummary,
)
from backend.schemas import (
    BacktestStrategyJobCreate,
    BacktestStrategyJobRead,
    ContractBreakdown,
    ContractBreakdownItem,
    ContractTickerBreakdownItem,
    BacktestEventSummary,
    BacktestHistogram,
    BacktestRunDetail,
    BacktestRunSummary,
    BacktestSignalPage,
    BacktestSignalRead,
    BacktestStatRead,
    BacktestUniverseMemberCreate,
    BacktestUniverseMemberRead,
    BacktestUniverseMemberUpdate,
    DailyRallyCandidateRead,
    DailyRallyCandidatesRead,
    DailyRallyInsightsRead,
    DailyRallyPatternStatRead,
    DailyRallyPatternStatsRead,
    DailyRallyReturnStatRead,
    DailyRallyRuleStatRead,
    DailyRallyValidationRead,
    HistogramBin,
)
from backend.timezone import seoul_now
from scripts.backtest.daily_rally import DAILY_RALLY_STRATEGY_KIND, run_daily_rally_backtest
from scripts.backtest.engine import SignalRecord, WARMUP_WEEKS, run_span2_breakout_backtest
from scripts.backtest.persistence import persist_daily_rally_run, persist_run
from scripts.backtest.preload_daily import preload_daily_bars
from scripts.backtest.universe import normalize_korean_ticker

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

_RET_COLUMN = {
    4: BacktestSignal.ret_4w,
    8: BacktestSignal.ret_8w,
    12: BacktestSignal.ret_12w,
    26: BacktestSignal.ret_26w,
}
_ACTIVE_PRELOAD_JOB_STATUSES = ("pending", "running")
_ACTIVE_STRATEGY_JOB_STATUSES = ("pending", "running")
_SPAN2_STRATEGY_KIND = "ichimoku_span2_breakout"
_DAILY_RALLY_STRATEGY_KIND = DAILY_RALLY_STRATEGY_KIND
_CONTRACT_FOCUS_THRESHOLD = 12
_CONTRACT_TICKER_MIN_ENTRIES = 5


def _universe_member_or_404(db: Session, ticker: str) -> BacktestUniverseMember:
    normalized = _normalize_universe_ticker(ticker)
    member = db.get(BacktestUniverseMember, normalized)
    if member is None:
        raise HTTPException(status_code=404, detail="Backtest universe member not found")
    return member


def _normalize_universe_ticker(ticker: str) -> str:
    try:
        return normalize_korean_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _create_preload_job_if_needed(
    db: Session,
    member: BacktestUniverseMember,
) -> BacktestPreloadJob | None:
    existing_job = db.scalar(
        select(BacktestPreloadJob)
        .where(
            BacktestPreloadJob.ticker == member.ticker,
            BacktestPreloadJob.status.in_(_ACTIVE_PRELOAD_JOB_STATUSES),
        )
        .order_by(BacktestPreloadJob.id.desc())
    )
    if existing_job is not None:
        return None

    preload_job = BacktestPreloadJob(ticker=member.ticker, name=member.name)
    db.add(preload_job)
    db.flush()
    return preload_job


@router.get("/universe", response_model=list[BacktestUniverseMemberRead])
def list_universe_members(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
) -> list[BacktestUniverseMemberRead]:
    stmt = select(BacktestUniverseMember).where(BacktestUniverseMember.market == "KR")
    if not include_inactive:
        stmt = stmt.where(BacktestUniverseMember.active.is_(True))
    members = list(
        db.scalars(
            stmt.order_by(BacktestUniverseMember.sort_order, BacktestUniverseMember.ticker)
        ).all()
    )
    return [BacktestUniverseMemberRead.model_validate(member) for member in members]


@router.post(
    "/universe",
    response_model=BacktestUniverseMemberRead,
    status_code=status.HTTP_201_CREATED,
)
def create_universe_member(
    payload: BacktestUniverseMemberCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> BacktestUniverseMemberRead:
    ticker = _normalize_universe_ticker(payload.ticker)
    if db.get(BacktestUniverseMember, ticker) is not None:
        raise HTTPException(status_code=409, detail="Backtest universe member already exists")

    member = BacktestUniverseMember(
        ticker=ticker,
        name=payload.name.strip(),
        market=payload.market,
        active=payload.active,
        sort_order=payload.sort_order,
        source=payload.source.strip() or "manual",
    )
    db.add(member)
    db.flush()
    preload_job = _create_preload_job_if_needed(db, member)
    preload_job_id = preload_job.id if preload_job is not None else None
    db.commit()
    db.refresh(member)
    if preload_job_id is not None:
        background_tasks.add_task(run_backtest_preload_pipeline, preload_job_id)
    return BacktestUniverseMemberRead.model_validate(member)


def run_backtest_preload_pipeline(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(BacktestPreloadJob, job_id)
        if job is None:
            return

        job.status = "running"
        db.commit()

        result = preload_daily_bars(db, universe=[(job.ticker, job.name)])
        job.processed = result.processed
        job.skipped = result.skipped
        job.upserted_rows = result.upserted_rows
        job.completed_at = seoul_now()
        if result.failed:
            job.status = "failed"
            job.error_message = "; ".join(
                f"{ticker} {name}: {message}" for ticker, name, message in result.failed
            )
        else:
            job.status = "done"
            job.error_message = None
        db.commit()
    except Exception as exc:
        job = db.get(BacktestPreloadJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = seoul_now()
            db.commit()
    finally:
        db.close()


@router.post(
    "/strategy-jobs",
    response_model=BacktestStrategyJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_strategy_job_endpoint(
    payload: BacktestStrategyJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> BacktestStrategyJobRead:
    existing = db.scalar(
        select(BacktestStrategyJob)
        .where(BacktestStrategyJob.status.in_(_ACTIVE_STRATEGY_JOB_STATUSES))
        .order_by(BacktestStrategyJob.id.desc())
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Backtest strategy job is already running",
        )

    job = BacktestStrategyJob(strategy_kind=payload.strategy_kind)
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(run_backtest_strategy_pipeline, job.id)
    return BacktestStrategyJobRead.model_validate(job)


@router.get("/strategy-jobs", response_model=list[BacktestStrategyJobRead])
def list_strategy_jobs_endpoint(db: Session = Depends(get_db)) -> list[BacktestStrategyJobRead]:
    jobs = list(
        db.scalars(
            select(BacktestStrategyJob).order_by(BacktestStrategyJob.id.desc()).limit(20)
        ).all()
    )
    return [BacktestStrategyJobRead.model_validate(job) for job in jobs]


@router.get("/strategy-jobs/{job_id}", response_model=BacktestStrategyJobRead)
def get_strategy_job_endpoint(
    job_id: int,
    db: Session = Depends(get_db),
) -> BacktestStrategyJobRead:
    job = db.get(BacktestStrategyJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest strategy job not found")
    return BacktestStrategyJobRead.model_validate(job)


def run_backtest_strategy_pipeline(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(BacktestStrategyJob, job_id)
        if job is None:
            return
        job.status = "running"
        job.error_message = None
        db.commit()

        if job.strategy_kind == _SPAN2_STRATEGY_KIND:
            result = run_span2_breakout_backtest(db)
            run_id = persist_run(
                db,
                buy_threshold=0,
                warmup_weeks=WARMUP_WEEKS,
                ticker_count=result.ticker_count,
                records=result.records,
                stats=result.stats,
                data_start=result.data_start,
                data_end=result.data_end,
                notes="ichimoku span2 breakout; weekly close execution",
                strategy_kind=_SPAN2_STRATEGY_KIND,
                horizons="event",
                universe="KOSPI200-DB",
            )
        elif job.strategy_kind == _DAILY_RALLY_STRATEGY_KIND:
            result = run_daily_rally_backtest(db)
            run_id = persist_daily_rally_run(db, result)
        else:
            raise ValueError(f"Unsupported strategy_kind: {job.strategy_kind}")
        job = db.get(BacktestStrategyJob, job_id)
        if job is not None:
            job.status = "done"
            job.backtest_run_id = run_id
            job.error_message = None
            job.completed_at = seoul_now()
            db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(BacktestStrategyJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error_message = str(exc)[:2000]
            job.completed_at = seoul_now()
            db.commit()
    finally:
        db.close()


@router.patch("/universe/{ticker}", response_model=BacktestUniverseMemberRead)
def update_universe_member(
    ticker: str,
    payload: BacktestUniverseMemberUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> BacktestUniverseMemberRead:
    member = _universe_member_or_404(db, ticker)
    was_active = member.active
    if payload.name is not None:
        member.name = payload.name.strip()
    if payload.active is not None:
        member.active = payload.active
    if payload.sort_order is not None:
        member.sort_order = payload.sort_order
    preload_job = None
    if payload.active is True and not was_active:
        preload_job = _create_preload_job_if_needed(db, member)
    preload_job_id = preload_job.id if preload_job is not None else None
    db.commit()
    db.refresh(member)
    if preload_job_id is not None:
        background_tasks.add_task(run_backtest_preload_pipeline, preload_job_id)
    return BacktestUniverseMemberRead.model_validate(member)


@router.delete("/universe/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
def delete_universe_member(
    ticker: str,
    db: Session = Depends(get_db),
) -> Response:
    member = _universe_member_or_404(db, ticker)
    member.active = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _adj_signal_counts(db: Session, run_ids: list[int]) -> dict[int, int]:
    """H4 기준 8-9 버킷 제외한 신호 수를 run_id별로 반환."""
    if not run_ids:
        return {}
    rows = db.execute(
        select(BacktestStat.run_id, func.sum(BacktestStat.count))
        .where(
            BacktestStat.run_id.in_(run_ids),
            BacktestStat.horizon == 4,
            BacktestStat.score_bucket.not_in(["ALL", "8-9"]),
        )
        .group_by(BacktestStat.run_id)
    ).all()
    return {row[0]: int(row[1]) for row in rows}


def _daily_rally_run_or_404(db: Session, run_id: int) -> BacktestRun:
    run = db.get(BacktestRun, run_id)
    if run is None or run.strategy_kind != _DAILY_RALLY_STRATEGY_KIND:
        raise HTTPException(status_code=404, detail="Daily Rally backtest run not found")
    return run


def _planned_contract_returns(
    analysis: Analysis | None,
) -> tuple[float | None, float | None, float | None]:
    if (
        analysis is None
        or analysis.entry_price is None
        or analysis.target_price is None
        or analysis.stop_loss is None
        or analysis.entry_price <= 0
    ):
        return None, None, None

    target_return = analysis.target_price / analysis.entry_price - 1
    stop_return = analysis.stop_loss / analysis.entry_price - 1
    risk = abs(stop_return)
    risk_reward = target_return / risk if risk > 0 else None
    return target_return, stop_return, risk_reward


def _event_summary(db: Session, run: BacktestRun) -> BacktestEventSummary:
    signals = list(
        db.scalars(
            select(BacktestSignal).where(BacktestSignal.run_id == run.id)
        ).all()
    )
    entered = [signal for signal in signals if signal.exit_reason != "no_entry"]
    returns = [signal.event_return for signal in entered if signal.event_return is not None]
    gains = [event_return for event_return in returns if event_return > 0]
    losses = [event_return for event_return in returns if event_return < 0]
    days = [signal.days_held for signal in entered if signal.days_held is not None]
    target_count = sum(1 for signal in signals if signal.exit_reason == "target")
    stop_count = sum(1 for signal in signals if signal.exit_reason == "stop")
    open_count = sum(1 for signal in signals if signal.exit_reason == "open")
    expiry_count = sum(1 for signal in signals if signal.exit_reason == "expiry")
    no_entry_count = sum(1 for signal in signals if signal.exit_reason == "no_entry")
    mean_return = float(np.mean(returns)) if returns else None
    avg_gain_return = float(np.mean(gains)) if gains else None
    avg_loss_return = float(np.mean(losses)) if losses else None
    realized_payoff_ratio = (
        avg_gain_return / abs(avg_loss_return)
        if avg_gain_return is not None and avg_loss_return is not None and avg_loss_return != 0
        else None
    )
    source_analysis = db.get(Analysis, run.source_analysis_id) if run.source_analysis_id else None
    planned_target_return, planned_stop_return, planned_risk_reward_ratio = (
        _planned_contract_returns(source_analysis)
    )
    target_hit_rate = (target_count / len(entered)) if entered else None
    positive_return_rate = (
        sum(1 for event_return in returns if event_return > 0) / len(returns)
        if returns
        else None
    )
    win_rate = positive_return_rate if run.strategy_kind == _SPAN2_STRATEGY_KIND else target_hit_rate
    return BacktestEventSummary(
        signal_count=len(signals),
        entered_count=len(entered),
        no_entry_count=no_entry_count,
        target_count=target_count,
        stop_count=stop_count,
        open_count=open_count,
        expiry_count=expiry_count,
        target_hit_rate=target_hit_rate,
        positive_return_rate=positive_return_rate,
        win_rate=win_rate,
        mean_return=mean_return,
        expectancy=mean_return,
        median_return=float(np.median(returns)) if returns else None,
        avg_days_held=float(np.mean(days)) if days else None,
        planned_target_return=planned_target_return,
        planned_stop_return=planned_stop_return,
        planned_risk_reward_ratio=planned_risk_reward_ratio,
        avg_gain_return=avg_gain_return,
        avg_loss_return=avg_loss_return,
        realized_payoff_ratio=realized_payoff_ratio,
    )


def _contract_breakdown_item(signals: list[BacktestSignal]) -> ContractBreakdownItem:
    entered = [signal for signal in signals if signal.exit_reason != "no_entry"]
    returns = [signal.event_return for signal in entered if signal.event_return is not None]
    days = [signal.days_held for signal in entered if signal.days_held is not None]
    target_count = sum(1 for signal in signals if signal.exit_reason == "target")
    stop_count = sum(1 for signal in signals if signal.exit_reason == "stop")
    expiry_count = sum(1 for signal in signals if signal.exit_reason == "expiry")
    no_entry_count = sum(1 for signal in signals if signal.exit_reason == "no_entry")

    return ContractBreakdownItem(
        signal_count=len(signals),
        entered_count=len(entered),
        no_entry_count=no_entry_count,
        target_count=target_count,
        stop_count=stop_count,
        expiry_count=expiry_count,
        target_hit_rate=(target_count / len(entered)) if entered else None,
        positive_return_rate=(
            sum(1 for event_return in returns if event_return > 0) / len(returns)
            if returns
            else None
        ),
        mean_return=float(np.mean(returns)) if returns else None,
        median_return=float(np.median(returns)) if returns else None,
        avg_days_held=float(np.mean(days)) if days else None,
    )


def _contract_breakdown(db: Session, run: BacktestRun) -> ContractBreakdown:
    signals = list(
        db.scalars(
            select(BacktestSignal)
            .where(BacktestSignal.run_id == run.id)
            .order_by(BacktestSignal.signal_date, BacktestSignal.id)
        ).all()
    )

    score_values = sorted({signal.score for signal in signals})
    by_score = {
        str(score): _contract_breakdown_item(
            [signal for signal in signals if signal.score == score]
        )
        for score in score_values
    }

    year_values = sorted({signal.signal_date.year for signal in signals})
    by_year = {
        str(year): _contract_breakdown_item(
            [signal for signal in signals if signal.signal_date.year == year]
        )
        for year in year_values
    }

    ticker_items: list[ContractTickerBreakdownItem] = []
    ticker_keys = sorted({(signal.ticker, signal.name) for signal in signals})
    for ticker, name in ticker_keys:
        ticker_signals = [
            signal for signal in signals if signal.ticker == ticker and signal.name == name
        ]
        item = _contract_breakdown_item(ticker_signals)
        if item.entered_count < _CONTRACT_TICKER_MIN_ENTRIES:
            continue
        ticker_items.append(
            ContractTickerBreakdownItem(
                **item.model_dump(),
                ticker=ticker,
                name=name,
            )
        )

    ticker_items.sort(
        key=lambda item: (
            item.mean_return is None,
            -(item.mean_return or 0),
            item.ticker,
        )
    )
    bottom_tickers = sorted(
        ticker_items,
        key=lambda item: (
            item.mean_return is None,
            item.mean_return or 0,
            item.ticker,
        ),
    )

    return ContractBreakdown(
        focus_threshold=_CONTRACT_FOCUS_THRESHOLD,
        focus=_contract_breakdown_item(
            [signal for signal in signals if signal.score >= _CONTRACT_FOCUS_THRESHOLD]
        ),
        by_score=by_score,
        by_year=by_year,
        top_tickers=ticker_items[:10],
        bottom_tickers=bottom_tickers[:10],
    )


@router.get("/runs", response_model=list[BacktestRunSummary])
def list_runs(db: Session = Depends(get_db)) -> list[BacktestRunSummary]:
    runs = list(
        db.scalars(
            select(BacktestRun).order_by(BacktestRun.id.desc())
        ).all()
    )
    adj = _adj_signal_counts(db, [run.id for run in runs])
    result = []
    for run in runs:
        summary = BacktestRunSummary.model_validate(run)
        if run.id in adj:
            summary.signal_count = adj[run.id]
        if run.source_analysis_id is not None:
            analysis = db.get(Analysis, run.source_analysis_id)
            if analysis is not None:
                summary.source_ticker = analysis.ticker
                summary.source_name = analysis.name
        result.append(summary)
    return result


@router.get("/runs/{run_id}", response_model=BacktestRunDetail)
def get_run(run_id: int, db: Session = Depends(get_db)) -> BacktestRunDetail:
    run = db.scalar(
        select(BacktestRun).where(BacktestRun.id == run_id)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="백테스트 실행을 찾을 수 없습니다.")

    stats = list(
        db.scalars(
            select(BacktestStat)
            .where(BacktestStat.run_id == run_id)
            .order_by(BacktestStat.horizon, BacktestStat.score_bucket)
        ).all()
    )
    summary = BacktestRunSummary.model_validate(run)
    adj = _adj_signal_counts(db, [run_id])
    if run_id in adj:
        summary.signal_count = adj[run_id]
    if run.source_analysis_id is not None:
        analysis = db.get(Analysis, run.source_analysis_id)
        if analysis is not None:
            summary.source_ticker = analysis.ticker
            summary.source_name = analysis.name
    return BacktestRunDetail(
        **summary.model_dump(),
        stats=[BacktestStatRead.model_validate(stat) for stat in stats],
        event_summary=_event_summary(db, run)
        if run.strategy_kind in {"analysis_contract", _SPAN2_STRATEGY_KIND}
        else None,
        contract_breakdown=_contract_breakdown(db, run)
        if run.strategy_kind == "analysis_contract"
        else None,
    )


@router.get("/runs/{run_id}/daily-rally-insights", response_model=DailyRallyInsightsRead)
def get_daily_rally_insights(
    run_id: int,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> DailyRallyInsightsRead:
    _daily_rally_run_or_404(db, run_id)
    rules = list(
        db.scalars(
            select(DailyRallyRuleStat)
            .where(DailyRallyRuleStat.run_id == run_id)
            .order_by(
                DailyRallyRuleStat.score.desc(),
                DailyRallyRuleStat.precision.desc(),
                DailyRallyRuleStat.support.desc(),
            )
            .limit(limit)
        ).all()
    )
    return DailyRallyInsightsRead(
        run_id=run_id,
        rule_count=len(rules),
        rules=[DailyRallyRuleStatRead.model_validate(rule) for rule in rules],
    )


@router.get(
    "/runs/{run_id}/daily-rally-pattern-stats",
    response_model=DailyRallyPatternStatsRead,
)
def get_daily_rally_pattern_stats(
    run_id: int,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> DailyRallyPatternStatsRead:
    _daily_rally_run_or_404(db, run_id)
    patterns = list(
        db.scalars(
            select(DailyRallyPatternStat)
            .where(DailyRallyPatternStat.run_id == run_id)
            .order_by(
                DailyRallyPatternStat.score.desc(),
                DailyRallyPatternStat.precision.desc(),
                DailyRallyPatternStat.support.desc(),
            )
            .limit(limit)
        ).all()
    )
    return DailyRallyPatternStatsRead(
        run_id=run_id,
        pattern_count=len(patterns),
        patterns=[
            DailyRallyPatternStatRead(
                id=pattern.id,
                run_id=pattern.run_id,
                pattern_key=pattern.pattern_key,
                pattern_label=pattern.pattern_label,
                support=pattern.support,
                positives=pattern.positives,
                total_matches=pattern.total_matches,
                precision=pattern.precision,
                base_rate=pattern.base_rate,
                lift=pattern.lift,
                score=pattern.score,
                return_stats=[
                    DailyRallyReturnStatRead(**value)
                    for _horizon, value in sorted(
                        json.loads(pattern.return_stats_json).items(),
                        key=lambda item: int(item[0]),
                    )
                ],
            )
            for pattern in patterns
        ],
    )


@router.get("/runs/{run_id}/daily-rally-candidates", response_model=DailyRallyCandidatesRead)
def get_daily_rally_candidates(
    run_id: int,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> DailyRallyCandidatesRead:
    _daily_rally_run_or_404(db, run_id)
    candidates = list(
        db.scalars(
            select(DailyRallyCurrentCandidate)
            .where(DailyRallyCurrentCandidate.run_id == run_id)
            .order_by(
                DailyRallyCurrentCandidate.composite_score.is_(None).asc(),
                DailyRallyCurrentCandidate.composite_score.desc(),
                DailyRallyCurrentCandidate.max_rule_score.desc(),
                DailyRallyCurrentCandidate.matched_rule_count.desc(),
                DailyRallyCurrentCandidate.ticker.asc(),
            )
            .limit(limit)
        ).all()
    )
    return DailyRallyCandidatesRead(
        run_id=run_id,
        candidate_count=len(candidates),
        candidates=[
            DailyRallyCandidateRead(
                id=candidate.id,
                run_id=candidate.run_id,
                ticker=candidate.ticker,
                name=candidate.name,
                signal_date=candidate.signal_date,
                close_price=candidate.close_price,
                matched_rules=json.loads(candidate.matched_rules_json),
                matched_rule_count=candidate.matched_rule_count,
                max_rule_score=candidate.max_rule_score,
                mean_rule_score=candidate.mean_rule_score,
                features=json.loads(candidate.features_json),
                composite_score=candidate.composite_score,
                best_rule_key=candidate.best_rule_key,
                rule_quality_score=candidate.rule_quality_score,
                stability_score=candidate.stability_score,
                stability_classification=candidate.stability_classification,
                expected_return_score=candidate.expected_return_score,
                expected_win_rate_20d=candidate.expected_win_rate_20d,
                expected_median_return_20d=candidate.expected_median_return_20d,
                rule_breakdowns=json.loads(candidate.score_breakdown_json or "[]"),
            )
            for candidate in candidates
        ],
    )


@router.get("/runs/{run_id}/daily-rally-validation", response_model=DailyRallyValidationRead)
def get_daily_rally_validation(
    run_id: int,
    db: Session = Depends(get_db),
) -> DailyRallyValidationRead:
    _daily_rally_run_or_404(db, run_id)
    validation = db.scalar(
        select(DailyRallyValidationSummary)
        .where(DailyRallyValidationSummary.run_id == run_id)
        .order_by(DailyRallyValidationSummary.id.desc())
    )
    if validation is None:
        raise HTTPException(status_code=404, detail="Daily Rally validation summary not found")
    payload = json.loads(validation.summary_json)
    return DailyRallyValidationRead(run_id=run_id, **payload)


@router.get("/runs/{run_id}/signals", response_model=BacktestSignalPage)
def list_signals(
    run_id: int,
    ticker: str | None = None,
    score_bucket: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> BacktestSignalPage:
    if db.get(BacktestRun, run_id) is None:
        raise HTTPException(status_code=404, detail="백테스트 실행을 찾을 수 없습니다.")

    stmt = select(BacktestSignal).where(BacktestSignal.run_id == run_id)
    if ticker:
        stmt = stmt.where(BacktestSignal.ticker == ticker)
    if score_bucket:
        stmt = stmt.where(BacktestSignal.score_bucket == score_bucket)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(db.scalar(total_stmt) or 0)
    items = list(
        db.scalars(
            stmt.order_by(BacktestSignal.signal_date, BacktestSignal.id).offset(offset).limit(limit)
        ).all()
    )
    return BacktestSignalPage(
        total=total,
        items=[BacktestSignalRead.model_validate(item) for item in items],
    )


@router.get("/runs/{run_id}/histogram", response_model=BacktestHistogram)
def get_histogram(
    run_id: int,
    horizon: int = Query(4),
    score_bucket: str = Query("ALL"),
    bins: int = Query(20, ge=5, le=60),
    db: Session = Depends(get_db),
) -> BacktestHistogram:
    if db.get(BacktestRun, run_id) is None:
        raise HTTPException(status_code=404, detail="백테스트 실행을 찾을 수 없습니다.")

    column = _RET_COLUMN.get(horizon)
    if column is None:
        raise HTTPException(status_code=400, detail="지원하지 않는 horizon")

    stmt = select(column).where(BacktestSignal.run_id == run_id, column.is_not(None))
    if score_bucket != "ALL":
        stmt = stmt.where(BacktestSignal.score_bucket == score_bucket)

    values = [float(value) for value in db.scalars(stmt).all()]
    if not values:
        return BacktestHistogram(horizon=horizon, score_bucket=score_bucket, bins=[])

    counts, edges = np.histogram(np.array(values), bins=bins)
    return BacktestHistogram(
        horizon=horizon,
        score_bucket=score_bucket,
        bins=[
            HistogramBin(lower=float(edges[index]), upper=float(edges[index + 1]), count=int(counts[index]))
            for index in range(len(counts))
        ],
    )
