from __future__ import annotations


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
