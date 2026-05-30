from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import String, cast, func, select, update
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import create_database_engine  # noqa: E402
from backend.models import BacktestRun, BacktestSignal, BacktestStat  # noqa: E402
from scripts.backtest.analysis_similarity import SIMILARITY_BUCKETS  # noqa: E402
from scripts.backtest.engine import SignalRecord, aggregate  # noqa: E402


@dataclass(frozen=True, slots=True)
class RebucketingResult:
    run_id: int
    updated_signals: int
    deleted_stats: int
    inserted_stats: int
    dry_run: bool


def _record_from_signal(signal: BacktestSignal) -> SignalRecord:
    return SignalRecord(
        ticker=signal.ticker,
        name=signal.name,
        signal_date=signal.signal_date,
        score=signal.score,
        score_bucket=str(signal.score),
        entry_date=signal.entry_date,
        entry_price=signal.entry_price,
        returns={
            4: signal.ret_4w,
            8: signal.ret_8w,
            12: signal.ret_12w,
            26: signal.ret_26w,
        },
    )


def rebucket_similarity_run(
    db: Session,
    *,
    run_id: int,
    dry_run: bool = True,
) -> RebucketingResult:
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise ValueError(f"Backtest run not found: {run_id}")
    if run.strategy_kind != "analysis_similarity":
        raise ValueError(f"Run {run_id} is not an analysis_similarity run")

    signals = list(
        db.scalars(
            select(BacktestSignal)
            .where(BacktestSignal.run_id == run_id)
            .order_by(BacktestSignal.id)
        ).all()
    )
    records = [_record_from_signal(signal) for signal in signals]
    stats = aggregate(records, buckets=SIMILARITY_BUCKETS)

    existing_stats_count = int(
        db.scalar(select(func.count()).where(BacktestStat.run_id == run_id)) or 0
    )
    changed_signals = sum(
        1 for signal in signals if signal.score_bucket != str(signal.score)
    )

    if dry_run:
        return RebucketingResult(
            run_id=run_id,
            updated_signals=changed_signals,
            deleted_stats=existing_stats_count,
            inserted_stats=len(stats),
            dry_run=True,
        )

    db.execute(
        update(BacktestSignal)
        .where(BacktestSignal.run_id == run_id)
        .values(score_bucket=cast(BacktestSignal.score, String(10)))
    )
    db.query(BacktestStat).filter(BacktestStat.run_id == run_id).delete(
        synchronize_session=False
    )
    for stat in stats:
        db.add(
            BacktestStat(
                run_id=run_id,
                horizon=stat.horizon,
                score_bucket=stat.score_bucket,
                count=stat.count,
                censored_count=stat.censored_count,
                win_rate=stat.win_rate,
                mean=stat.mean,
                median=stat.median,
                std=stat.std,
                p25=stat.p25,
                p75=stat.p75,
                min=stat.min,
                max=stat.max,
            )
        )
    db.commit()
    return RebucketingResult(
        run_id=run_id,
        updated_signals=changed_signals,
        deleted_stats=existing_stats_count,
        inserted_stats=len(stats),
        dry_run=False,
    )


def rebucket_all_similarity_runs(
    db: Session,
    *,
    dry_run: bool = True,
) -> list[RebucketingResult]:
    run_ids = list(
        db.scalars(
            select(BacktestRun.id)
            .where(BacktestRun.strategy_kind == "analysis_similarity")
            .order_by(BacktestRun.id)
        ).all()
    )
    return [
        rebucket_similarity_run(db, run_id=run_id, dry_run=dry_run)
        for run_id in run_ids
    ]


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild analysis-similarity backtest stats with exact score buckets."
    )
    parser.add_argument("--run-id", type=int, default=None)
    parser.add_argument("--apply", action="store_true", help="Write changes instead of dry-run")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    engine = create_database_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        if args.run_id is None:
            results = rebucket_all_similarity_runs(db, dry_run=not args.apply)
        else:
            results = [rebucket_similarity_run(db, run_id=args.run_id, dry_run=not args.apply)]

    for result in results:
        mode = "DRY" if result.dry_run else "APPLIED"
        print(
            f"{mode} run={result.run_id} "
            f"signals={result.updated_signals} "
            f"stats={result.deleted_stats}->{result.inserted_stats}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
