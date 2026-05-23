"""Render SKILL.md-compatible markdown from rule scorer output."""
from __future__ import annotations

from .features import Features
from .levels import Levels
from .score import ScoreResult


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "없음"
    return f"{value:,.0f}원"


def _lag_label(lag_above: bool | None) -> str:
    if lag_above is True:
        return "가격선 위"
    if lag_above is False:
        return "가격선 아래"
    return "교차 중"


def _cloud_direction(direction: str | None) -> str:
    if direction in ("상승운", "하락운", "전환 예정"):
        return direction
    return "전환 예정"


def render_markdown(features: Features, score: ScoreResult, levels: Levels) -> str:
    top = score.top_components(3)
    while len(top) < 3:
        top.append(type(top[0]) if top else None)  # placeholder, never reached

    notes_line = (", ".join(score.notes)) if score.notes else "없음"

    # Build entry rows. For 매도 both 없음. For 매수/홀드, include both rows but
    # mark unavailable ones as 없음 so parser can still pick a valid entry.
    if score.judgment == "매도":
        pullback_str = "없음"
        breakout_str = "없음"
        target_str = "없음"
        stop_str = "없음"
    else:
        pullback_str = _fmt_price(levels.entry_pullback)
        breakout_str = _fmt_price(levels.entry_breakout)
        target_str = _fmt_price(levels.target)
        stop_str = _fmt_price(levels.stop)

    rationale_lines = []
    for i, comp in enumerate(score.top_components(3), start=1):
        rationale_lines.append(f"{i}. {comp.detail} (score {comp.score:+d})")
    while len(rationale_lines) < 3:
        rationale_lines.append(f"{len(rationale_lines) + 1}. 추가 근거 없음")

    return f"""## 종목 분석 결과

### 1. 현재 구조 요약
- 추세: {score.trend}
- 구름대 위치: {score.cloud_position}
- MA 배열: {score.ma_alignment}
- 후행스팬: {_lag_label(features.lag_above_price)}

### 2. 핵심 지지/저항선
- 1차 지지: {_fmt_price(levels.support_1)}  근거: 전환선/MA20
- 2차 지지: {_fmt_price(levels.support_2)}  근거: 기준선/구름 하단
- 1차 저항: {_fmt_price(levels.resistance_1)}  근거: 전환선/구름 상단
- 2차 저항: {_fmt_price(levels.resistance_2)}  근거: 최근 52주 고가

### 3. 향후 구름 전망 (미래 26주)
- 구름 방향: {_cloud_direction(features.future_cloud_direction)}
- 비고: 룰 기반 스코어러 자동 판정 (total score {score.total:+d})

### 4. 매매 판정
**{score.judgment}**
근거:
{rationale_lines[0]}
{rationale_lines[1]}
{rationale_lines[2]}
주의사항:
- NaN 또는 데이터 부족 컴포넌트: {notes_line}

### 5. 진입/청산 시나리오
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 눌림 진입 | 지지선 부근 조정 시 매수 | {pullback_str} |
| 돌파 진입 | 최근 12주 고가 종가 돌파 시 추격 | {breakout_str} |
| 1차 목표 | ATR/52주 고가 기반 저항 도달 | {target_str} |
| 손절 기준 | 기준선 또는 1.5 ATR 하향 이탈 (종가 기준) | {stop_str} |
"""
