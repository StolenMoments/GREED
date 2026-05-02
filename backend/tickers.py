from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO


US_MARKETS = ("NASDAQ", "NYSE", "AMEX")


@dataclass(frozen=True)
class UsStockListing:
    code: str
    name: str
    market: str


def is_korean_ticker(ticker: str) -> bool:
    return ticker.strip().isdigit()


def is_korean_text(text: str) -> bool:
    return any('가' <= c <= '힣' or 'ㄱ' <= c <= 'ㅎ' for c in text)


def normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if normalized.isdigit():
        return normalized.zfill(6)
    return normalized


def market_for_ticker(ticker: str) -> str:
    return "KR" if is_korean_ticker(ticker) else "US"


def fetch_us_listing() -> list[UsStockListing]:
    import FinanceDataReader as fdr

    stocks_by_code: dict[str, UsStockListing] = {}
    for market in US_MARKETS:
        try:
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                listing = fdr.StockListing(market)
        except Exception:
            continue

        code_col = next(
            (col for col in listing.columns if col in ("Code", "Symbol", "ticker")),
            None,
        )
        name_col = next(
            (col for col in listing.columns if col in ("Name", "CompanyName", "name")),
            None,
        )
        if code_col is None or name_col is None:
            continue

        for _, row in listing.iterrows():
            code = str(row[code_col]).strip().upper()
            name = str(row[name_col]).strip()
            if code and name and code not in stocks_by_code:
                stocks_by_code[code] = UsStockListing(code=code, name=name, market=market)

    return list(stocks_by_code.values())
