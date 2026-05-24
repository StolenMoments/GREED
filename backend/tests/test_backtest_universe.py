import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from backtest.universe import load_universe  # noqa: E402


def test_load_universe_parses_code_name(tmp_path):
    csv = tmp_path / "u.csv"
    csv.write_text(
        "code,name\n5930,삼성전자\n000660,SK하이닉스\n",
        encoding="utf-8-sig",
    )

    rows = load_universe(csv)

    assert rows == [("005930", "삼성전자"), ("000660", "SK하이닉스")]


def test_load_universe_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_universe(tmp_path / "nope.csv")


def test_load_universe_empty_raises(tmp_path):
    csv = tmp_path / "u.csv"
    csv.write_text("code,name\n", encoding="utf-8-sig")

    with pytest.raises(ValueError):
        load_universe(csv)
