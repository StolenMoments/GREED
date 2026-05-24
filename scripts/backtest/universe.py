from __future__ import annotations

import csv
from pathlib import Path

DEFAULT_UNIVERSE_PATH = Path(__file__).resolve().parent / "kospi200.csv"


def load_universe(path: Path | str = DEFAULT_UNIVERSE_PATH) -> list[tuple[str, str]]:
    """Read a code,name CSV into normalized six-digit ticker/name pairs."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"KOSPI200 universe file does not exist: {p}\n"
            "Create a CSV with code,name columns at that path."
        )

    rows: list[tuple[str, str]] = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if len(row) < 2:
                continue
            code = row[0].strip().zfill(6)
            name = row[1].strip()
            if code.isdigit() and len(code) == 6:
                rows.append((code, name))

    if not rows:
        raise ValueError(f"Universe file has no valid tickers: {p}")
    return rows
