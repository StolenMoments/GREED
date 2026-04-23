from __future__ import annotations

HANGUL_BASE = 0xAC00
HANGUL_END = 0xD7A3
HANGUL_SYLLABLE_COUNT_PER_INITIAL = 21 * 28
KOREAN_INITIALS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
KOREAN_INITIAL_SET = set(KOREAN_INITIALS)


def extract_korean_initials(value: str) -> str:
    initials: list[str] = []

    for char in value:
        code = ord(char)
        if HANGUL_BASE <= code <= HANGUL_END:
            initial_index = (code - HANGUL_BASE) // HANGUL_SYLLABLE_COUNT_PER_INITIAL
            initials.append(KOREAN_INITIALS[initial_index])

    return "".join(initials)


def is_korean_initial_query(value: str) -> bool:
    return bool(value) and all(char in KOREAN_INITIAL_SET for char in value)
