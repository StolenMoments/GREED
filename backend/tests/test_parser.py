from __future__ import annotations

from backend.parser import parse_markdown


def test_parse_markdown_extracts_required_and_optional_fields() -> None:
    markdown = """
## 종목 분석 결과

### 1. 현재 구조 요약
- 추세: 상승
- 구름대 위치: 구름 위
- MA 배열: 정배열

### 4. 매매 판정
**매수**

### 5. 진입/청산 시나리오
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 진입 조건 | 20주선 지지 확인 | 75,000원 |
| 1차 목표 | 전고점 재도전 | 82,000 |
| 손절 기준 | 추세 이탈 | 71,500원 |
"""

    result = parse_markdown(markdown)

    assert result.success is True
    assert result.failed == []
    assert result.data == {
        "judgment": "매수",
        "trend": "상승",
        "cloud_position": "구름 위",
        "ma_alignment": "정배열",
        "entry_price": 75000.0,
        "target_price": 82000.0,
        "stop_loss": 71500.0,
    }


def test_parse_markdown_accepts_bold_required_field_labels() -> None:
    markdown = """
## 판단
**홀드** (신규 진입은 단기 눌림목 대기)

---

## 기술적 지표 요약
- **추세**: 상승 (2025년 4월 저점 134,600 → 현재 260,000, +93%)
- **구름대 위치**: 구름 위 (현재가 260,000 / 선행스팬1: 203,500 / 선행스팬2: 191,300)
- **MA 배열**: 정배열 (Close 260,000 > MA20 224,900 > MA60 200,668 > MA120 196,605)

---

## 매매 전략

| 구분 | 조건 | 가격대 |
|------|------|--------|
| 진입 조건 | 단기 눌림 대기 | 245,000 |
| 1차 목표 | 전고점 재도전 | 280,000 |
| 손절 기준 | 추세 훼손 | 230,000 |
"""

    result = parse_markdown(markdown)

    assert result.success is True
    assert result.failed == []
    assert result.data["judgment"] == "홀드"
    assert result.data["trend"] == "상승"
    assert result.data["cloud_position"] == "구름 위"
    assert result.data["ma_alignment"] == "정배열"


def test_parse_markdown_reports_missing_required_field() -> None:
    markdown = """
## 종목 분석 결과

### 1. 현재 구조 요약
- 추세: 횡보
- 구름대 위치: 구름 안
- MA 배열: 혼조
"""

    result = parse_markdown(markdown)

    assert result.success is False
    assert result.failed == ["judgment"]
    assert result.data["trend"] == "횡보"
    assert result.data["cloud_position"] == "구름 안"
    assert result.data["ma_alignment"] == "혼조"
    assert result.data["entry_price"] is None
    assert result.data["target_price"] is None
    assert result.data["stop_loss"] is None


def test_parse_markdown_uses_lower_bound_for_price_ranges() -> None:
    markdown = """
### 1. 현재 구조 요약
- 추세: 상승
- 구름대 위치: 구름 위
- MA 배열: 정배열

### 4. 매매 판정
**홀드**

### 5. 진입/청산 시나리오
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 진입 조건 | 눌림 대기 | 53,000 ~ 55,000원 |
| 1차 목표 | 단기 반등 | 58,500원 |
| 손절 기준 | 지지선 하향 이탈 | 51,000원 |
"""

    result = parse_markdown(markdown)

    assert result.success is True
    assert result.data["judgment"] == "홀드"
    assert result.data["entry_price"] == 53000.0


def test_parse_markdown_returns_none_for_na_tokens() -> None:
    markdown = """
### 1. 현재 구조 요약
- 추세: 하락
- 구름대 위치: 구름 아래
- MA 배열: 역배열

### 4. 매매 판정
**매도**

### 5. 진입/청산 시나리오
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 진입 조건 | 반등 시 분할 대응 | N/A |
| 1차 목표 | 미정 | 미정 |
| 손절 기준 | 의미 없음 | - |
"""

    result = parse_markdown(markdown)

    assert result.success is True
    assert result.data["entry_price"] is None
    assert result.data["target_price"] is None
    assert result.data["stop_loss"] is None


def test_parse_markdown_falls_back_to_plain_judgment_text() -> None:
    markdown = """
### 1. 현재 구조 요약
- 추세: 상승
- 구름대 위치: 구름 위
- MA 배열: 정배열

### 4. 매매 판정
매수

### 5. 진입/청산 시나리오
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 진입 조건 | 눌림목 진입 | 75,000 |
| 1차 목표 | 돌파 확인 | 81,000 |
| 손절 기준 | 구조 훼손 | 72,000 |
"""

    result = parse_markdown(markdown)

    assert result.success is True
    assert result.data["judgment"] == "매수"


def test_parse_markdown_accepts_bracketed_judgment_text() -> None:
    markdown = """
### 1. 현재 구조 요약
- 추세: 상승
- 구름대 위치: 구름 위
- MA 배열: 혼조

### 4. 매매 판정
[매수]
"""

    result = parse_markdown(markdown)

    assert result.success is True
    assert result.data["judgment"] == "매수"


def test_parse_markdown_accepts_quoted_judgment_text() -> None:
    markdown = """
### 1. 현재 구조 요약
- 추세: 하락
- 구름대 위치: 구름 아래
- MA 배열: 역배열

### 4. 매매 판정
"매도"
"""

    result = parse_markdown(markdown)

    assert result.success is True
    assert result.data["judgment"] == "매도"


def test_parse_markdown_extracts_transformed_example_markdown_table() -> None:
    markdown = """
## 종목 분석 결과

### 1. 현재 구조 요약
- 추세: 상승
- 구름대 위치: 구름 위
- MA 배열: 혼조
- 후행스팬: 가격선 위

### 2. 핵심 지지/저항선
- 1차 지지: 2,106원 근거: 일목 전환선
- 2차 지지: 2,023원 근거: 120주 이동평균선
- 1차 저항: 2,216원 근거: 일목 기준선
- 2차 저항: 2,500원 근거: 최근 단기 전고점 (2026년 3월 23일 주간 고가)

### 3. 향후 구름 전망 (미래 26주)
- 구름 방향: 전환 예정
- 비고: 향후 26주 미래 구름은 초반 하락운을 유지하다가 2026년 7월경 얇은 상승운으로 전환된 뒤 다시 혼조세가 전개됩니다.

### 4. 매매 판정
[매수]

### 5. 진입/청산 시나리오
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 진입 조건 | 1차 지지선(전환선) 부근 눌림 시 분할 매수 또는 1차 저항선(기준선) 상향 돌파 시 추격 매수 | 2,100원 ~ 2,220원 |
| 1차 목표 | 최근 형성된 매물대 상단 및 직전 파동의 의미 있는 고점 도달 | 2,500원 |
| 손절 기준 | 주가가 120주 이동평균선 및 20주 이동평균선을 동시 하향 이탈하며 추세 지지 무효화 | 1,990원 미만 |
"""

    result = parse_markdown(markdown)

    assert result.success is True
    assert result.failed == []
    assert result.data["judgment"] == "매수"
    assert result.data["trend"] == "상승"
    assert result.data["cloud_position"] == "구름 위"
    assert result.data["ma_alignment"] == "혼조"
    assert result.data["entry_price"] == 2100.0
    assert result.data["target_price"] == 2500.0
    assert result.data["stop_loss"] == 1990.0


def test_parse_markdown_accepts_colon_inside_bold_with_modifier() -> None:
    """LLM sometimes outputs '**필드:** 수식어 값' — colon inside bold + modifier word."""
    markdown = """
### 1. 현재 구조 요약

- **추세:** 강한 상승 (전주 70,400 → 118,900, 주간 +68.9%)
- **구름대 위치:** 구름 위 (종가 118,900 >> 구름 상단 35,925)
- **MA 배열:** 정배열 (MA20 > MA60 > MA120)

### 4. 매매 판정
**매수**

### 5. 진입/청산 시나리오
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 진입 조건 | 눌림 대기 | 110,000 |
| 1차 목표 | 전고점 | 130,000 |
| 손절 기준 | 추세 이탈 | 100,000 |
"""

    result = parse_markdown(markdown)

    assert result.success is True
    assert result.failed == []
    assert result.data["judgment"] == "매수"
    assert result.data["trend"] == "상승"
    assert result.data["cloud_position"] == "구름 위"
    assert result.data["ma_alignment"] == "정배열"


def test_parse_markdown_accepts_bracketed_bold_judgment() -> None:
    """LLM follows the system prompt template literally: **[매수]** instead of **매수**."""
    markdown = """
### 1. 현재 구조 요약
- 추세: 상승
- 구름대 위치: 구름 위
- MA 배열: 정배열

### 4. 매매 판정
**[매수]**
"""

    result = parse_markdown(markdown)

    assert result.success is True
    assert result.data["judgment"] == "매수"


def test_parse_markdown_collects_all_failed_required_fields() -> None:
    result = parse_markdown("")

    assert result.success is False
    assert result.failed == ["judgment", "trend", "cloud_position", "ma_alignment"]
