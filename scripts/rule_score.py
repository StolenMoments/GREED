"""Rule-based scorer CLI — produces analyses with model="rule".

Reads each weekly CSV under --pick-dir, computes a deterministic score and
markdown, and POSTs to the greed backend's /api/analyses endpoint.

Usage:
    python scripts/rule_score.py [--run-id N] [--pick-dir scripts/pick_output]
                                  [--api http://localhost:8000] [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rule_scorer import (  # noqa: E402
    compute_levels,
    extract_features,
    render_markdown,
    score_features,
)
from rule_scorer.features import load_csv  # noqa: E402


FILENAME_RE = re.compile(
    r"^(?P<market>[^_]+)_(?P<ticker>[^_]+)_(?P<name>.+)_weekly_\d{8}\.csv$"
)


def _parse_filename(path: Path) -> tuple[str, str, str] | None:
    match = FILENAME_RE.match(path.name)
    if not match:
        return None
    return match.group("market"), match.group("ticker"), match.group("name")


def _ensure_run(api: str, run_id: int | None) -> int:
    if run_id is not None:
        return run_id
    memo = f"{datetime.now().strftime('%Y%m%d')} 룰 자동 분석"
    resp = requests.post(f"{api}/api/runs", json={"memo": memo}, timeout=30)
    resp.raise_for_status()
    return int(resp.json()["id"])


def _process_csv(
    api: str,
    run_id: int,
    path: Path,
    dry_run: bool,
) -> tuple[bool, str]:
    parsed = _parse_filename(path)
    if parsed is None:
        return False, f"파일명 패턴 불일치: {path.name}"
    _, ticker, name = parsed

    try:
        df = load_csv(path)
        features = extract_features(df)
        score = score_features(features)
        levels = compute_levels(features, score.judgment)
        markdown = render_markdown(features, score, levels)
    except Exception as exc:
        return False, f"분석 실패: {exc}"

    if dry_run:
        print(markdown)
        return True, f"[DRY] {ticker} {name} — {score.judgment} (score {score.total:+d})"

    payload = {
        "run_id": run_id,
        "ticker": ticker,
        "name": name,
        "model": "rule",
        "markdown": markdown,
        "judgment": score.judgment,
        "trend": score.trend,
        "cloud_position": score.cloud_position,
        "ma_alignment": score.ma_alignment,
    }
    resp = requests.post(f"{api}/api/analyses", json=payload, timeout=60)
    if resp.status_code == 201:
        return True, f"[OK] {ticker} {name} — {score.judgment}"
    if resp.status_code == 422:
        try:
            failed = resp.json().get("failed_fields", [])
        except Exception:
            failed = []
        return False, f"[FAIL] {ticker} — 파싱 실패: {failed}"
    return False, f"[FAIL] {ticker} — HTTP {resp.status_code}: {resp.text[:200]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pick-dir", default="scripts/pick_output")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--run-id", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="마크다운만 stdout 출력, API 호출 없음")
    args = parser.parse_args()

    pick_dir = Path(args.pick_dir)
    if not pick_dir.exists():
        print(f"[ERROR] pick_dir 없음: {pick_dir}", file=sys.stderr)
        return 2

    csv_paths = sorted(pick_dir.glob("*_weekly_*.csv"))
    if not csv_paths:
        print(f"[ERROR] CSV 없음: {pick_dir}", file=sys.stderr)
        return 2

    run_id = 0 if args.dry_run else _ensure_run(args.api, args.run_id)

    success = 0
    failure = 0
    for path in csv_paths:
        ok, message = _process_csv(args.api, run_id, path, args.dry_run)
        print(message)
        if ok:
            success += 1
        else:
            failure += 1

    print(f"\n성공: {success}개 / 실패: {failure}개 / Run ID: {run_id}")
    return 0 if failure == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
