from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal, ensure_database_ready  # noqa: E402
from scripts.backtest.universe import DEFAULT_UNIVERSE_PATH, import_universe_csv  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Import backtest universe members from CSV.")
    parser.add_argument("--path", default=str(DEFAULT_UNIVERSE_PATH))
    parser.add_argument("--source", default="kospi200.csv")
    args = parser.parse_args()

    ensure_database_ready()
    db = SessionLocal()
    try:
        count = import_universe_csv(db, args.path, source=args.source)
    finally:
        db.close()

    print(f"Imported {count} backtest universe members from {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
