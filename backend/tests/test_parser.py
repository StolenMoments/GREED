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


def test_parse_markdown_collects_all_failed_required_fields() -> None:
    result = parse_markdown("")

    assert result.success is False
    assert result.failed == ["judgment", "trend", "cloud_position", "ma_alignment"]
