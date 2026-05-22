from __future__ import annotations

import re
from dataclasses import dataclass


REQUIRED_FIELDS = ("judgment", "trend", "cloud_position", "ma_alignment")
OPTIONAL_FIELDS = ("entry_price", "target_price", "stop_loss")
# "없음", "none" 은 스펙 외 방어적 추가 — LLM 출력 변형 대응
NONE_TOKENS = {"n/a", "na", "-", "미정", "없음", "none"}
PRICE_VALUE_PATTERN = re.compile(r"\d[\d,]*(?:\.\d+)?")

FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    # \*{0,2}\s* after colon handles "**필드:** 값" (colon inside bold markers)
    # (?:[가-힣]+\s+)? handles LLM modifier words like "강한 상승" → "상승"
    "trend": re.compile(r"\*{0,2}추세\*{0,2}\s*:\s*\*{0,2}\s*(?:[가-힣]+\s+)?(상승|하락|횡보)"),
    "cloud_position": re.compile(
        r"\*{0,2}구름대 위치\*{0,2}\s*:\s*\*{0,2}\s*(구름 위|구름 안|구름 아래)",
    ),
    "ma_alignment": re.compile(r"\*{0,2}MA 배열\*{0,2}\s*:\s*\*{0,2}\s*(정배열|역배열|혼조)"),
}

PRICE_PATTERNS: dict[str, re.Pattern[str]] = {
    "target_price": re.compile(r"^\|\s*1차\s*목표[^|]*\|.*?\|\s*([^|\n]+)\|?\s*$", re.MULTILINE),
    "stop_loss": re.compile(r"^\|\s*손절 기준\s*\|.*?\|\s*([^|\n]+)\|?\s*$", re.MULTILINE),
}
ENTRY_LABEL_PRIORITY = {"눌림": 0, "진입": 1, "돌파": 2}

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

    for field_name, pattern in PRICE_PATTERNS.items():
        match = pattern.search(markdown)
        price_min, price_max = _parse_price(match.group(1)) if match is not None else (None, None)
        data[field_name] = price_min
        data[f"{field_name}_max"] = price_max

    entry_candidates = parse_entry_candidates(markdown)
    selected_entry = _select_representative_entry_candidate(
        candidates=entry_candidates,
        data=data,
    )
    if selected_entry is None and entry_candidates:
        selected_entry = _preferred_entry_candidate(entry_candidates)

    data["entry_price"] = selected_entry.price if selected_entry is not None else None
    data["entry_price_max"] = selected_entry.price_max if selected_entry is not None else None

    if _has_price_consistency_error(data, entry_candidates):
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


def _select_representative_entry_candidate(
    candidates: list[EntryCandidate],
    data: dict[str, str | float | None],
) -> EntryCandidate | None:
    if not candidates:
        return None

    if data.get("judgment") not in {"매수", "홀드"}:
        return _preferred_entry_candidate(candidates)

    for candidate in sorted(candidates, key=_entry_candidate_sort_key):
        if _is_price_consistent_for_entry(candidate, data):
            return candidate

    return None


def _preferred_entry_candidate(candidates: list[EntryCandidate]) -> EntryCandidate:
    return sorted(candidates, key=_entry_candidate_sort_key)[0]


def _entry_candidate_sort_key(candidate: EntryCandidate) -> tuple[int, float]:
    return (ENTRY_LABEL_PRIORITY.get(candidate.label, ENTRY_LABEL_PRIORITY["진입"]), candidate.price)


def _is_price_consistent_for_entry(
    candidate: EntryCandidate,
    data: dict[str, str | float | None],
) -> bool:
    entry_low = min(candidate.price, candidate.price_max) if candidate.price_max is not None else candidate.price
    entry_high = max(candidate.price, candidate.price_max) if candidate.price_max is not None else candidate.price

    target_min = _as_float(data.get("target_price"))
    target_max = _as_float(data.get("target_price_max")) or target_min
    if target_max is not None and target_max < entry_high:
        return False

    stop_min = _as_float(data.get("stop_loss"))
    if stop_min is not None and stop_min > entry_low:
        return False

    return True


def _parse_price_values(raw_values: list[str]) -> tuple[float | None, float | None]:
    values: list[float] = []
    for raw_value in raw_values:
        cleaned = raw_value.strip()
        if not cleaned or cleaned.casefold() in NONE_TOKENS:
            continue

        values.extend(float(n.replace(",", "")) for n in PRICE_VALUE_PATTERN.findall(cleaned))

    if not values:
        return None, None

    lo, hi = min(values), max(values)
    return lo, (hi if hi != lo else None)


def _has_price_consistency_error(
    data: dict[str, str | float | None],
    entry_candidates: list[EntryCandidate],
) -> bool:
    # 매도는 보유분 정리/진입 회피 의미로 쓰이므로 롱 포지션 가격 관계를 강제하지 않는다.
    if data.get("judgment") not in {"매수", "홀드"}:
        return False

    if entry_candidates and not any(
        _is_price_consistent_for_entry(candidate, data) for candidate in entry_candidates
    ):
        return True

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
