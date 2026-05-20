from __future__ import annotations

HANGUL_BASE = 0xAC00
HANGUL_END = 0xD7A3
HANGUL_SYLLABLE_COUNT_PER_INITIAL = 21 * 28
KOREAN_INITIALS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
KOREAN_INITIAL_SET = set(KOREAN_INITIALS)
COMPOUND_KOREAN_INITIALS = {
    "ㄳ": "ㄱㅅ",
    "ㄵ": "ㄴㅈ",
    "ㄶ": "ㄴㅎ",
    "ㄺ": "ㄹㄱ",
    "ㄻ": "ㄹㅁ",
    "ㄼ": "ㄹㅂ",
    "ㄽ": "ㄹㅅ",
    "ㄾ": "ㄹㅌ",
    "ㄿ": "ㄹㅍ",
    "ㅀ": "ㄹㅎ",
    "ㅄ": "ㅂㅅ",
}


def extract_korean_initials(value: str) -> str:
    initials: list[str] = []

    for char in value:
        code = ord(char)
        if HANGUL_BASE <= code <= HANGUL_END:
            initial_index = (code - HANGUL_BASE) // HANGUL_SYLLABLE_COUNT_PER_INITIAL
            initials.append(KOREAN_INITIALS[initial_index])

    return "".join(initials)


def normalize_korean_initial_query(value: str) -> str:
    return "".join(COMPOUND_KOREAN_INITIALS.get(char, char) for char in value)


def is_korean_initial_query(value: str) -> bool:
    normalized = normalize_korean_initial_query(value)
    return bool(normalized) and all(char in KOREAN_INITIAL_SET for char in normalized)
