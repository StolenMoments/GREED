"""KOSPI200 룰 매수 신호 백테스트 CLI.

사용법:
    python -m scripts.backtest.run [--universe scripts/backtest/kospi200.csv]
                                   [--warmup 120] [--limit N] [--notes "..."]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # 프로젝트 루트
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from backend.database import SessionLocal, ensure_database_ready  # noqa: E402
from rule_scorer.score import BUY_THRESHOLD  # noqa: E402

from backtest.data import load_weekly_ohlcv  # noqa: E402
from backtest.engine import (  # noqa: E402
    WARMUP_WEEKS,
    aggregate,
    build_combined,
    run_span2_breakout_ticker,
    run_ticker,
)
from backtest.persistence import persist_run  # noqa: E402
from backtest.universe import load_active_universe, load_universe  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default=None, help="Optional CSV universe override.")
    parser.add_argument("--warmup", type=int, default=WARMUP_WEEKS)
    parser.add_argument("--limit", type=int, default=None, help="종목 수 제한(디버그)")
    parser.add_argument("--notes", default=None)
    parser.add_argument(
        "--strategy",
        choices=["rule", "ichimoku_span2_breakout"],
        default="rule",
    )
    args = parser.parse_args()

    ensure_database_ready()
    db = SessionLocal()
    all_records = []
    data_start: date | None = None
    data_end: date | None = None
    processed = 0
    try:
        try:
            universe = load_universe(args.universe) if args.universe else load_active_universe(db)
            universe_name = "CSV" if args.universe else "KOSPI200-DB"
        except (FileNotFoundError, ValueError) as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 2
        if args.limit:
            universe = universe[: args.limit]

        for code, name in universe:
            try:
                weekly = load_weekly_ohlcv(db, code)
            except Exception as exc:
                print(f"[WARN] {code} {name} 데이터 적재 실패: {exc}", file=sys.stderr)
                continue
            if weekly.empty or len(weekly) <= args.warmup + 1:
                print(f"[SKIP] {code} {name} 주봉 부족({len(weekly)})")
                continue
            combined = build_combined(weekly, code, name)
            records = (
                run_span2_breakout_ticker(combined, warmup=args.warmup)
                if args.strategy == "ichimoku_span2_breakout"
                else run_ticker(combined, warmup=args.warmup)
            )
            all_records.extend(records)
            processed += 1
            first = weekly.index.min().date()
            last = weekly.index.max().date()
            data_start = first if data_start is None else min(data_start, first)
            data_end = last if data_end is None else max(data_end, last)
            print(f"[OK] {code} {name}: 신호 {len(records)}개")

        stats = [] if args.strategy == "ichimoku_span2_breakout" else aggregate(all_records)
        run_id = persist_run(
            db,
            buy_threshold=0 if args.strategy == "ichimoku_span2_breakout" else BUY_THRESHOLD,
            warmup_weeks=args.warmup,
            ticker_count=processed,
            records=all_records,
            stats=stats,
            data_start=data_start,
            data_end=data_end,
            notes=args.notes,
            strategy_kind=args.strategy if args.strategy != "rule" else None,
            horizons="event" if args.strategy == "ichimoku_span2_breakout" else None,
            universe=universe_name,
        )
    finally:
        db.close()

    print(f"\n완료: 종목 {processed}개 / 신호 {len(all_records)}개 / Run ID {run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
