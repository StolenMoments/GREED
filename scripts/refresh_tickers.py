"""
refresh_tickers.py
KRX/US 종목 목록을 FinanceDataReader에서 받아 DB에 갱신합니다.

사용법:
    python scripts/refresh_tickers.py          # KRX + US 전체 갱신
    python scripts/refresh_tickers.py --krx    # KRX만
    python scripts/refresh_tickers.py --us     # US만
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.crud import refresh_krx_listing, refresh_us_listing
from backend.database import SessionLocal, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh ticker listings in DB")
    parser.add_argument("--krx", action="store_true", help="KRX 종목만 갱신")
    parser.add_argument("--us", action="store_true", help="US 종목만 갱신")
    args = parser.parse_args()

    refresh_all = not args.krx and not args.us

    init_db()
    db = SessionLocal()
    try:
        if refresh_all or args.krx:
            print("KRX 종목 갱신 중...")
            refresh_krx_listing(db)
            print("KRX 완료.")
        if refresh_all or args.us:
            print("US 종목 갱신 중... (NASDAQ/NYSE/AMEX)")
            refresh_us_listing(db)
            print("US 완료.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
