"""Rule-based scoring on extracted features."""
from __future__ import annotations

from dataclasses import dataclass, field

from .features import Features


BUY_THRESHOLD = 4
SELL_THRESHOLD = -2


@dataclass(slots=True)
class Component:
    name: str
    score: int
    detail: str


@dataclass(slots=True)
class ScoreResult:
    judgment: str  # 매수 / 홀드 / 매도
    total: int
    trend: str  # 상승 / 하락 / 횡보
    cloud_position: str  # 구름 위 / 구름 안 / 구름 아래
    ma_alignment: str  # 정배열 / 역배열 / 혼조
    components: list[Component] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def top_components(self, n: int = 3) -> list[Component]:
        return sorted(
            (c for c in self.components if c.score != 0),
            key=lambda c: abs(c.score),
            reverse=True,
        )[:n]


def _classify_cloud_position(f: Features) -> str:
    if f.cloud_top is None or f.cloud_bottom is None:
        return "구름 안"
    if f.close > f.cloud_top:
        return "구름 위"
    if f.close < f.cloud_bottom:
        return "구름 아래"
    return "구름 안"


def _classify_ma_alignment(f: Features) -> str:
    if f.ma20 is None or f.ma60 is None or f.ma120 is None:
        return "혼조"
    if f.ma20 > f.ma60 > f.ma120:
        return "정배열"
    if f.ma20 < f.ma60 < f.ma120:
        return "역배열"
    return "혼조"


def _classify_trend(ma_alignment: str) -> str:
    if ma_alignment == "정배열":
        return "상승"
    if ma_alignment == "역배열":
        return "하락"
    return "횡보"


def score_features(f: Features) -> ScoreResult:
    components: list[Component] = []
    notes: list[str] = []

    cloud_position = _classify_cloud_position(f)
    ma_alignment = _classify_ma_alignment(f)
    trend = _classify_trend(ma_alignment)

    # 1) Cloud position
    if cloud_position == "구름 위":
        components.append(Component(
            "cloud", +2,
            f"종가 {f.close:,.0f} > 구름 상단 {f.cloud_top:,.0f}",
        ))
    elif cloud_position == "구름 아래":
        components.append(Component(
            "cloud", -2,
            f"종가 {f.close:,.0f} < 구름 하단 {f.cloud_bottom:,.0f}",
        ))
    else:
        components.append(Component("cloud", 0, "구름 안 또는 데이터 부족"))
        if f.cloud_top is None or f.cloud_bottom is None:
            notes.append("skipped: cloud (NaN)")

    # 2) MA alignment
    if ma_alignment == "정배열":
        components.append(Component(
            "ma_alignment", +2,
            f"MA20 {f.ma20:,.0f} > MA60 {f.ma60:,.0f} > MA120 {f.ma120:,.0f}",
        ))
    elif ma_alignment == "역배열":
        components.append(Component(
            "ma_alignment", -2,
            f"MA20 {f.ma20:,.0f} < MA60 {f.ma60:,.0f} < MA120 {f.ma120:,.0f}",
        ))
    else:
        components.append(Component("ma_alignment", 0, "MA 혼조"))
        if f.ma20 is None or f.ma60 is None or f.ma120 is None:
            notes.append("skipped: ma_alignment (NaN)")

    # 3) MACD hist momentum (2주 연속)
    if f.macd_hist is None or f.macd_hist_prev is None or f.macd_hist_prev2 is None:
        components.append(Component("macd_hist", 0, "MACD hist 데이터 부족"))
        notes.append("skipped: macd_hist (NaN)")
    else:
        rising = f.macd_hist > f.macd_hist_prev > f.macd_hist_prev2
        falling = f.macd_hist < f.macd_hist_prev < f.macd_hist_prev2
        if f.macd_hist > 0 and rising:
            components.append(Component(
                "macd_hist", +1,
                f"MACD hist {f.macd_hist:+.2f} (전주 {f.macd_hist_prev:+.2f}) 2주 연속 증가",
            ))
        elif f.macd_hist < 0 and falling:
            components.append(Component(
                "macd_hist", -1,
                f"MACD hist {f.macd_hist:+.2f} (전주 {f.macd_hist_prev:+.2f}) 2주 연속 감소",
            ))
        else:
            components.append(Component(
                "macd_hist", 0,
                f"MACD hist {f.macd_hist:+.2f} 모멘텀 미확인",
            ))

    # 4) RSI
    if f.rsi14 is None:
        components.append(Component("rsi", 0, "RSI 데이터 부족"))
        notes.append("skipped: rsi (NaN)")
    elif 45 <= f.rsi14 <= 65:
        components.append(Component("rsi", +1, f"RSI {f.rsi14:.1f} 회복 구간"))
    elif f.rsi14 > 75:
        components.append(Component("rsi", -1, f"RSI {f.rsi14:.1f} 과열"))
    else:
        components.append(Component("rsi", 0, f"RSI {f.rsi14:.1f} 중립"))

    # 5) Volume ratio
    if f.volume_ratio_20 is None:
        components.append(Component("volume", 0, "거래량비 데이터 부족"))
        notes.append("skipped: volume (NaN)")
    elif f.volume_ratio_20 >= 1.0:
        components.append(Component(
            "volume", +1, f"volume_ratio_20 {f.volume_ratio_20:.2f} 평균 이상",
        ))
    elif f.volume_ratio_20 < 0.7:
        components.append(Component(
            "volume", -1, f"volume_ratio_20 {f.volume_ratio_20:.2f} 위축",
        ))
    else:
        components.append(Component(
            "volume", 0, f"volume_ratio_20 {f.volume_ratio_20:.2f} 평균 수준",
        ))

    # 6) Close vs ichi conv/base
    if f.ichi_conv is None or f.ichi_base is None:
        components.append(Component("ichi_lines", 0, "전환/기준선 데이터 부족"))
        notes.append("skipped: ichi_lines (NaN)")
    elif f.close > f.ichi_conv and f.close > f.ichi_base:
        components.append(Component(
            "ichi_lines", +1,
            f"종가 {f.close:,.0f} > 전환선 {f.ichi_conv:,.0f} 및 기준선 {f.ichi_base:,.0f}",
        ))
    else:
        components.append(Component(
            "ichi_lines", 0,
            f"종가 {f.close:,.0f} vs 전환선 {f.ichi_conv:,.0f}/기준선 {f.ichi_base:,.0f}",
        ))

    # 7) Strict divergence
    if f.strict_divergence == "bullish":
        components.append(Component("divergence", +1, "strict_divergence=bullish"))
    elif f.strict_divergence == "bearish":
        components.append(Component("divergence", -2, "strict_divergence=bearish"))
    else:
        components.append(Component("divergence", 0, "다이버전스 없음"))

    # 8) MA20/60 recent cross
    if f.ma20_60_cross_recent == "golden":
        components.append(Component("ma_cross", +1, "최근 4주 ma20_60_cross=golden"))
    elif f.ma20_60_cross_recent == "dead":
        components.append(Component("ma_cross", -1, "최근 4주 ma20_60_cross=dead"))
    else:
        components.append(Component("ma_cross", 0, "최근 4주 ma20/60 교차 없음"))

    # 9) Future cloud direction
    if f.future_cloud_direction == "상승운":
        components.append(Component("future_cloud", +1, "미래 구름 상승운"))
    elif f.future_cloud_direction == "하락운":
        components.append(Component("future_cloud", -1, "미래 구름 하락운"))
    else:
        components.append(Component(
            "future_cloud", 0,
            f"미래 구름 {f.future_cloud_direction or '판단 불가'}",
        ))
        if f.future_cloud_direction is None:
            notes.append("skipped: future_cloud (NaN)")

    total = sum(c.score for c in components)
    if total >= BUY_THRESHOLD:
        judgment = "매수"
    elif total <= SELL_THRESHOLD:
        judgment = "매도"
    else:
        judgment = "홀드"

    return ScoreResult(
        judgment=judgment,
        total=total,
        trend=trend,
        cloud_position=cloud_position,
        ma_alignment=ma_alignment,
        components=components,
        notes=notes,
    )
