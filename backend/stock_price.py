from __future__ import annotations

from datetime import date, timedelta


def fetch_latest_close(ticker: str) -> tuple[date, float] | None:
    import FinanceDataReader as fdr

    start = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")
    end = date.today().strftime("%Y-%m-%d")
    df = fdr.DataReader(ticker, start, end)
    if df.empty:
        return None
    last = df.iloc[-1]
    price_date = last.name.date() if hasattr(last.name, "date") else date.today()
    return price_date, float(last["Close"])
