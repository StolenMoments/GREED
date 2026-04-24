"""Merge runs + analyses from a source greed.db into a target greed.db.

Both databases share the same schema (backend/models.py). Because `runs.id`
and `analyses.id` are autoincrement, rows from the source cannot be inserted
directly — they would collide with the target's existing IDs. This script
re-maps `runs.id` and rewrites `analyses.run_id` accordingly.

Scope (by design):
  - runs, analyses only.
  - stock_prices, analysis_jobs are NOT touched.

Usage (run on the TARGET notebook):

    .venv/Scripts/python.exe scripts/merge_db.py \\
        --source greed_source.db \\
        --target greed.db \\
        [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.models import Analysis, Run


def _make_session_factory(db_path: Path) -> sessionmaker[Session]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def merge(source_path: Path, target_path: Path, *, dry_run: bool) -> None:
    SourceSession = _make_session_factory(source_path)
    TargetSession = _make_session_factory(target_path)

    with SourceSession() as src, TargetSession() as dst:
        source_runs = src.query(Run).order_by(Run.id).all()
        if not source_runs:
            print("source 에 runs 가 없습니다. 종료.")
            return

        run_id_map: dict[int, int] = {}
        new_run_ids: list[int] = []

        for src_run in source_runs:
            new_run = Run(memo=src_run.memo, created_at=src_run.created_at)
            dst.add(new_run)
            dst.flush()
            run_id_map[src_run.id] = new_run.id
            new_run_ids.append(new_run.id)

        source_analyses = src.query(Analysis).order_by(Analysis.id).all()
        inserted_analyses = 0
        for src_analysis in source_analyses:
            new_run_id = run_id_map.get(src_analysis.run_id)
            if new_run_id is None:
                raise RuntimeError(
                    f"analysis id={src_analysis.id} 의 run_id={src_analysis.run_id} "
                    "가 source runs 에 없습니다."
                )
            dst.add(
                Analysis(
                    run_id=new_run_id,
                    ticker=src_analysis.ticker,
                    name=src_analysis.name,
                    name_initials=src_analysis.name_initials,
                    model=src_analysis.model,
                    markdown=src_analysis.markdown,
                    judgment=src_analysis.judgment,
                    trend=src_analysis.trend,
                    cloud_position=src_analysis.cloud_position,
                    ma_alignment=src_analysis.ma_alignment,
                    entry_price=src_analysis.entry_price,
                    entry_price_max=src_analysis.entry_price_max,
                    target_price=src_analysis.target_price,
                    target_price_max=src_analysis.target_price_max,
                    stop_loss=src_analysis.stop_loss,
                    stop_loss_max=src_analysis.stop_loss_max,
                    created_at=src_analysis.created_at,
                )
            )
            inserted_analyses += 1

        if dry_run:
            dst.rollback()
            print("[DRY-RUN] rollback 완료. 실제 저장되지 않았습니다.")
        else:
            dst.commit()
            print("[COMMIT] 머지 완료.")

        print(f"  - runs: {len(source_runs)} 개 이전")
        if new_run_ids:
            print(f"    (새 run_id 범위: {min(new_run_ids)} ~ {max(new_run_ids)})")
        print(f"  - analyses: {inserted_analyses} 개 이전")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="source greed.db 경로")
    parser.add_argument("--target", required=True, type=Path, help="target greed.db 경로")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="rollback 하여 실제 저장하지 않고 insert 건수만 확인",
    )
    args = parser.parse_args()

    if args.source.resolve() == args.target.resolve():
        parser.error("source 와 target 이 같은 파일입니다.")

    merge(args.source, args.target, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
