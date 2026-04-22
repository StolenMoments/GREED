from __future__ import annotations

import re
from dataclasses import dataclass


REQUIRED_FIELDS = ("judgment", "trend", "cloud_position", "ma_alignment")
OPTIONAL_FIELDS = ("entry_price", "target_price", "stop_loss")
# "없음", "none" 은 스펙 외 방어적 추가 — LLM 출력 변형 대응
NONE_TOKENS = {"n/a", "na", "-", "미정", "없음", "none"}

FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    # \*{0,2}\s* after colon handles "**필드:** 값" (colon inside bold markers)
    # (?:[가-힣]+\s+)? handles LLM modifier words like "강한 상승" → "상승"
    "trend": re.compile(r"\*{0,2}추세\*{0,2}\s*:\s*\*{0,2}\s*(?:[가-힣]+\s+)?(상승|하락|횡보)"),
    "cloud_position": re.compile(
        r"\*{0,2}구름대 위치\*{0,2}\s*:\s*\*{0,2}\s*(구름 위|구름 안|구름 아래)",
    ),
    "ma_alignment": re.compile(r"\*{0,2}MA 배열\*{0,2}\s*:\s*\*{0,2}\s*(정배열|역배열|혼조)"),
}

# 3컬럼 테이블(구분|조건|가격대) 구조를 가정. 진입 행은 눌림/돌파 2개 행도 허용한다.
ENTRY_PRICE_PATTERN = re.compile(r"^\|\s*[^|\n]*진입[^|\n]*\|.*?\|\s*([^|\n]+)\|?\s*$", re.MULTILINE)
PRICE_PATTERNS: dict[str, re.Pattern[str]] = {
    "target_price": re.compile(r"^\|\s*1차\s*목표[^|]*\|.*?\|\s*([^|\n]+)\|?\s*$", re.MULTILINE),
    "stop_loss": re.compile(r"^\|\s*손절 기준\s*\|.*?\|\s*([^|\n]+)\|?\s*$", re.MULTILINE),
}

JUDGMENT_BOLD_PATTERN = re.compile(r"\*\*\[?\s*(매수|홀드|매도)\s*\]?\*\*")
JUDGMENT_FALLBACK_PATTERN = re.compile(
    r"^\s*(?:[-*]\s*)?(?:[\[\(\"'`]+)?(매수|홀드|매도)(?:[\]\)\"'`]+)?\s*$",
    re.MULTILINE,
)


@dataclass(slots=True)
class ParseResult:
    data: dict[str, str | float | None]
    failed: list[str]
    success: bool


@dataclass(slots=True)
class EntryCandidate:
    label: str
    price: float
    price_max: float | None


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

    entry_values = ENTRY_PRICE_PATTERN.findall(markdown)
    price_min, price_max = _parse_price_values(entry_values)
    data["entry_price"] = price_min
    data["entry_price_max"] = price_max

    for field_name, pattern in PRICE_PATTERNS.items():
        match = pattern.search(markdown)
        price_min, price_max = _parse_price(match.group(1)) if match is not None else (None, None)
        data[field_name] = price_min
        data[f"{field_name}_max"] = price_max

    if _has_price_consistency_error(data):
        failed.append("price_consistency")

    return ParseResult(
        data=data,
        failed=failed,
        success=not failed,
    )


def parse_entry_candidates(markdown: str) -> list[EntryCandidate]:
    candidates: list[EntryCandidate] = []
    for raw_label, raw_value in re.findall(
        r"^\|\s*([^|\n]*진입[^|\n]*)\|.*?\|\s*([^|\n]+)\|?\s*$",
        markdown,
        re.MULTILINE,
    ):
        price, price_max = _parse_price(raw_value)
        if price is None:
            continue
        candidates.append(
            EntryCandidate(
                label=_normalize_entry_label(raw_label),
                price=price,
                price_max=price_max,
            )
        )
    return candidates


def _extract_judgment(markdown: str) -> str | None:
    match = JUDGMENT_BOLD_PATTERN.search(markdown)
    if match is not None:
        return match.group(1)

    match = JUDGMENT_FALLBACK_PATTERN.search(markdown)
    if match is not None:
        return match.group(1)

    return None


def _parse_price(raw_value: str) -> tuple[float | None, float | None]:
    return _parse_price_values([raw_value])


def _normalize_entry_label(raw_label: str) -> str:
    if "눌림" in raw_label:
        return "눌림"
    if "돌파" in raw_label:
        return "돌파"
    return "진입"


def _parse_price_values(raw_values: list[str]) -> tuple[float | None, float | None]:
    values: list[float] = []
    for raw_value in raw_values:
        cleaned = raw_value.strip()
        if not cleaned or cleaned.casefold() in NONE_TOKENS:
            continue

        # 한국 주식 가격은 정수 전용 — 소수점 미지원 의도적 생략
        values.extend(float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", cleaned))

    if not values:
        return None, None

    lo, hi = min(values), max(values)
    return lo, (hi if hi != lo else None)


def _has_price_consistency_error(data: dict[str, str | float | None]) -> bool:
    # 매도는 보유분 정리/진입 회피 의미로 쓰이므로 롱 포지션 가격 관계를 강제하지 않는다.
    if data.get("judgment") not in {"매수", "홀드"}:
        return False

    entry_min = _as_float(data.get("entry_price"))
    if entry_min is None:
        return False
    entry_max = _as_float(data.get("entry_price_max")) or entry_min

    target_min = _as_float(data.get("target_price"))
    target_max = _as_float(data.get("target_price_max")) or target_min
    if target_max is not None and target_max < entry_max:
        return True

    stop_min = _as_float(data.get("stop_loss"))
    if stop_min is not None and stop_min > entry_min:
        return True

    return False


def _as_float(value: str | float | None) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
