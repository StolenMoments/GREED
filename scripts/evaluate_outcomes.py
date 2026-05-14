"""
판정 배치 실행 스크립트.

Usage:
    python -m scripts.evaluate_outcomes
    python -m scripts.evaluate_outcomes --force
"""
import argparse

from backend.database import SessionLocal, init_db
from backend.outcome import run_evaluate_outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description="분석 목표/손절 결과를 판정합니다.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="이미 저장된 판정 결과까지 다시 계산합니다.",
    )
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        result = run_evaluate_outcomes(db, force=args.force)
        print(f"완료: evaluated={result['evaluated']}, skipped={result['skipped']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
