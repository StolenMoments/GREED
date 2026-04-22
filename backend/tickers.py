from __future__ import annotations


def is_korean_ticker(ticker: str) -> bool:
    return ticker.strip().isdigit()


def normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if normalized.isdigit():
        return normalized.zfill(6)
    return normalized


def market_for_ticker(ticker: str) -> str:
    return "KR" if is_korean_ticker(ticker) else "US"
