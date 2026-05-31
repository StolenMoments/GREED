"""
최신 주봉 기준으로 분석 프로필과 유사한 현재 후보 종목을 스캔해 DB에 저장.

Usage:
    python -m scripts.backtest.scan_candidates --analysis-id 1266
    python -m scripts.backtest.scan_candidates --analysis-id 1266 --threshold 14
"""
from __future__ import annotations

import argparse
import sys

from backend.database import SessionLocal, init_db
from backend.models import Analysis, CurrentCandidate
from scripts.backtest.analysis_similarity import scan_current_candidates


def run(analysis_id: int, threshold: int) -> None:
    init_db()
    with SessionLocal() as db:
        analysis = db.get(Analysis, analysis_id)
        if analysis is None:
            print(f"Analysis {analysis_id} not found", file=sys.stderr)
            sys.exit(1)

        print(f"Scanning analysis={analysis_id} threshold={threshold} ...")
        candidates, scan_date = scan_current_candidates(db, analysis, threshold=threshold)
        print(f"scan_date={scan_date}  found={len(candidates)}")

        db.query(CurrentCandidate).filter(
            CurrentCandidate.analysis_id == analysis_id,
            CurrentCandidate.scan_date == scan_date,
        ).delete()

        for c in candidates:
            db.add(CurrentCandidate(
                analysis_id=analysis_id,
                scan_date=scan_date,
                ticker=c.ticker,
                name=c.name,
                score=c.score,
                current_close=c.current_close,
                entry_price=c.entry_price,
                target_price=c.target_price,
                stop_price=c.stop_price,
                entry_gap_pct=c.entry_gap_pct,
            ))
        db.commit()

        print(f"Saved {len(candidates)} rows")
        top = sorted(candidates, key=lambda x: (-x.score, x.entry_gap_pct))[:20]
        for c in top:
            print(
                f"  [{c.score}] {c.ticker} {c.name}: "
                f"close={c.current_close:.0f}  entry={c.entry_price:.0f}"
                f" (gap={c.entry_gap_pct:+.1f}%)  target={c.target_price:.0f}"
                f"  stop={c.stop_price:.0f}"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-id", type=int, required=True)
    parser.add_argument("--threshold", type=int, default=12)
    args = parser.parse_args()
    run(args.analysis_id, args.threshold)
