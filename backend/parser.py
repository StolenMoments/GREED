from __future__ import annotations

import re
from dataclasses import dataclass


REQUIRED_FIELDS = ("judgment", "trend", "cloud_position", "ma_alignment")
OPTIONAL_FIELDS = ("entry_price", "target_price", "stop_loss")
# "없음", "none" 은 스펙 외 방어적 추가 — LLM 출력 변형 대응
NONE_TOKENS = {"n/a", "na", "-", "미정", "없음", "none"}

FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "trend": re.compile(r"추세:\s*(상승|하락|횡보)"),
    "cloud_position": re.compile(r"구름대 위치:\s*(구름 위|구름 안|구름 아래)"),
    "ma_alignment": re.compile(r"MA 배열:\s*(정배열|역배열|혼조)"),
}

# 3컬럼 테이블(구분|조건|가격대) 구조를 가정. 컬럼 추가 시 패턴 재검토 필요.
PRICE_PATTERNS: dict[str, re.Pattern[str]] = {
    "entry_price": re.compile(r"^\|\s*진입 조건\s*\|.*?\|\s*([^|\n]+)\|?\s*$", re.MULTILINE),
    "target_price": re.compile(r"^\|\s*1차 목표\s*\|.*?\|\s*([^|\n]+)\|?\s*$", re.MULTILINE),
    "stop_loss": re.compile(r"^\|\s*손절 기준\s*\|.*?\|\s*([^|\n]+)\|?\s*$", re.MULTILINE),
}

JUDGMENT_BOLD_PATTERN = re.compile(r"\*\*(매수|홀드|매도)\*\*")
JUDGMENT_FALLBACK_PATTERN = re.compile(
    r"^\s*(?:[-*]\s*)?(매수|홀드|매도)\s*$",
    re.MULTILINE,
)


@dataclass(slots=True)
class ParseResult:
    data: dict[str, str | float | None]
    failed: list[str]
    success: bool


def parse_markdown(markdown: str) -> ParseResult:
    data: dict[str, str | float | None] = {}
    failed: list[str] = []

    judgment = _extract_judgment(markdown)
    if judgment is None:
        failed.append("judgment")
    else:
        data["judgment"] = judgment

    for field_name, pattern in FIELD_PATTERNS.items():
        match = pattern.search(markdown)
        if match is None:
            failed.append(field_name)
            continue
        data[field_name] = match.group(1).strip()

    for field_name, pattern in PRICE_PATTERNS.items():
        match = pattern.search(markdown)
        data[field_name] = _parse_price(match.group(1)) if match is not None else None

    return ParseResult(
        data=data,
        failed=failed,
        success=not failed,
    )


def _extract_judgment(markdown: str) -> str | None:
    match = JUDGMENT_BOLD_PATTERN.search(markdown)
    if match is not None:
        return match.group(1)

    match = JUDGMENT_FALLBACK_PATTERN.search(markdown)
    if match is not None:
        return match.group(1)

    return None


def _parse_price(raw_value: str) -> float | None:
    cleaned = raw_value.strip()
    if not cleaned:
        return None

    if cleaned.casefold() in NONE_TOKENS:
        return None

    # 한국 주식 가격은 정수 전용 — 소수점 미지원 의도적 생략
    number_match = re.search(r"\d[\d,]*", cleaned)
    if number_match is None:
        return None

    return float(number_match.group(0).replace(",", ""))
