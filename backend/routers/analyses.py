from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.crud import (
    create_analysis_backtest_job,
    create_analysis,
    delete_analysis,
    get_analyses,
    get_analyses_by_run,
    get_analyses_page,
    get_analysis,
    get_analysis_backtest_job,
    get_analysis_backtest_jobs,
    get_analysis_history,
    get_run,
    get_stock_price,
    mark_analysis_backtest_job_done,
    mark_analysis_backtest_job_failed,
    mark_analysis_backtest_job_running,
    upsert_stock_price,
)
from backend.database import SessionLocal, get_db
from backend.parser import parse_markdown
from backend.outcome import evaluate_single_outcome, run_evaluate_outcomes
from backend.schemas import (
    AnalysisBacktestJobCreate,
    AnalysisBacktestJobRead,
    AnalysisCreate,
    AnalysisPage,
    AnalysisRead,
    AnalysisSummary,
    EntryCandidateFilterEnum,
    EvaluateOutcomesResult,
    JudgmentEnum,
    OutcomeEnum,
)
from backend.stock_price import fetch_latest_close
from backend.tickers import normalize_ticker


router = APIRouter(tags=["analyses"])


@router.post("/api/analyses", response_model=AnalysisRead, status_code=status.HTTP_201_CREATED)
def create_analysis_endpoint(
    payload: AnalysisCreate,
    db: Session = Depends(get_db),
) -> AnalysisRead | Response:
    if get_run(db, payload.run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    parse_result = parse_markdown(payload.markdown)
    if not parse_result.success:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "파싱 실패", "failed_fields": parse_result.failed},
        )

    analysis_payload = payload.model_copy(update={"ticker": normalize_ticker(payload.ticker), **parse_result.data})
    return create_analysis(db, analysis_payload)


@router.get("/api/analyses", response_model=AnalysisPage)
def list_analyses_endpoint(
    judgment: JudgmentEnum | None = None,
    run_id: int | None = None,
    q: str | None = None,
    entry_gap_lte: float | None = Query(default=None, ge=0),
    entry_candidate: EntryCandidateFilterEnum = EntryCandidateFilterEnum.all,
    outcome: OutcomeEnum | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> AnalysisPage:
    judgment_value = judgment.value if judgment else None
    outcome_value = outcome.value if outcome else None
    if entry_gap_lte is not None:
        _refresh_candidate_stock_prices(db, judgment=judgment_value, run_id=run_id, q=q)

    return AnalysisPage(
        **get_analyses_page(
            db,
            judgment=judgment_value,
            run_id=run_id,
            q=q,
            entry_gap_lte=entry_gap_lte,
            entry_candidate=entry_candidate.value,
            outcome=outcome_value,
            page=page,
            page_size=page_size,
        )._asdict()
    )


@router.post("/api/analyses/evaluate-outcomes", response_model=EvaluateOutcomesResult)
def evaluate_outcomes_endpoint(
    force: bool = False,
    db: Session = Depends(get_db),
) -> EvaluateOutcomesResult:
    result = run_evaluate_outcomes(db, force=force)
    return EvaluateOutcomesResult(**result)


@router.get("/api/runs/{run_id}/analyses", response_model=list[AnalysisSummary])
def list_analyses_by_run_endpoint(
    run_id: int,
    judgment: JudgmentEnum | None = None,
    db: Session = Depends(get_db),
) -> list[AnalysisSummary]:
    if get_run(db, run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return get_analyses_by_run(db, run_id, judgment=judgment.value if judgment else None)


@router.get("/api/analyses/{analysis_id}", response_model=AnalysisRead)
def get_analysis_endpoint(
    analysis_id: int,
    db: Session = Depends(get_db),
) -> AnalysisRead:
    analysis = get_analysis(db, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return analysis


@router.post(
    "/api/analyses/{analysis_id}/backtest-jobs",
    response_model=AnalysisBacktestJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_analysis_backtest_job_endpoint(
    analysis_id: int,
    payload: AnalysisBacktestJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> AnalysisBacktestJobRead:
    if get_analysis(db, analysis_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    job = create_analysis_backtest_job(
        db,
        analysis_id=analysis_id,
        similarity_threshold=10,
    )
    background_tasks.add_task(run_analysis_backtest_pipeline, job.id)
    return job


@router.get(
    "/api/analyses/{analysis_id}/backtest-jobs",
    response_model=list[AnalysisBacktestJobRead],
)
def list_analysis_backtest_jobs_endpoint(
    analysis_id: int,
    db: Session = Depends(get_db),
) -> list[AnalysisBacktestJobRead]:
    if get_analysis(db, analysis_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return get_analysis_backtest_jobs(db, analysis_id)


@router.get(
    "/api/analyses/{analysis_id}/backtest-jobs/{job_id}",
    response_model=AnalysisBacktestJobRead,
)
def get_analysis_backtest_job_endpoint(
    analysis_id: int,
    job_id: int,
    db: Session = Depends(get_db),
) -> AnalysisBacktestJobRead:
    job = get_analysis_backtest_job(db, job_id)
    if job is None or job.analysis_id != analysis_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest job not found")
    return job


@router.post("/api/analyses/{analysis_id}/evaluate-outcome", response_model=AnalysisRead)
def evaluate_single_outcome_endpoint(
    analysis_id: int,
    db: Session = Depends(get_db),
) -> AnalysisRead:
    analysis = get_analysis(db, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    evaluate_single_outcome(db, analysis)
    return analysis


@router.delete("/api/analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis_endpoint(
    analysis_id: int,
    db: Session = Depends(get_db),
) -> Response:
    if not delete_analysis(db, analysis_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/analyses/{analysis_id}/history", response_model=list[AnalysisSummary])
def get_analysis_history_endpoint(
    analysis_id: int,
    db: Session = Depends(get_db),
) -> list[AnalysisSummary]:
    analysis = get_analysis(db, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return get_analysis_history(db, analysis.ticker)


def _refresh_candidate_stock_prices(
    db: Session,
    judgment: str | None,
    run_id: int | None,
    q: str | None,
) -> None:
    tickers = {
        analysis.ticker
        for analysis in get_analyses(db, judgment=judgment, run_id=run_id, q=q)
        if analysis.entry_price is not None
    }

    for raw_ticker in tickers:
        ticker = normalize_ticker(raw_ticker)
        cached = get_stock_price(db, ticker)
        if cached is not None and cached.price_date >= date.today():
            continue

        try:
            result = fetch_latest_close(ticker)
        except Exception:
            continue

        if result is None:
            continue

        price_date, close_price = result
        upsert_stock_price(db, ticker=ticker, price_date=price_date, close_price=close_price)


def run_analysis_backtest_pipeline(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = get_analysis_backtest_job(db, job_id)
        if job is None:
            return

        analysis = get_analysis(db, job.analysis_id)
        if analysis is None:
            mark_analysis_backtest_job_failed(db, job, error_message="Analysis not found")
            return

        try:
            mark_analysis_backtest_job_running(db, job)
            from scripts.backtest.analysis_similarity import run_analysis_contract_backtest
            from scripts.backtest.engine import WARMUP_WEEKS
            from scripts.backtest.persistence import persist_run

            result = run_analysis_contract_backtest(
                db,
                analysis,
                threshold=job.similarity_threshold,
            )
            run_id = persist_run(
                db,
                buy_threshold=job.similarity_threshold,
                warmup_weeks=WARMUP_WEEKS,
                ticker_count=result.ticker_count,
                records=result.records,
                stats=result.stats,
                data_start=result.data_start,
                data_end=result.data_end,
                notes=(
                    f"analysis_contract source_analysis_id={analysis.id}; "
                    f"base_score={result.base_score}; base_judgment={result.base_judgment}"
                ),
                source_analysis_id=analysis.id,
                strategy_kind="analysis_contract",
                similarity_threshold=job.similarity_threshold,
                horizons="contract",
            )
            mark_analysis_backtest_job_done(db, job, backtest_run_id=run_id)
        except Exception as exc:
            error_message = str(exc)
            db.rollback()
            failed_job = get_analysis_backtest_job(db, job_id)
            if failed_job is not None:
                mark_analysis_backtest_job_failed(db, failed_job, error_message=error_message)
    finally:
        db.close()
