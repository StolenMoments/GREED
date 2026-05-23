"""Compute entry / target / stop price levels from features."""
from __future__ import annotations

from dataclasses import dataclass

from .features import Features


@dataclass(slots=True)
class Levels:
    entry_pullback: float | None
    entry_breakout: float | None
    target: float | None
    stop: float | None
    support_1: float | None
    support_2: float | None
    resistance_1: float | None
    resistance_2: float | None


def _round_price(value: float | None) -> float | None:
    if value is None:
        return None
    return float(round(value))


def compute_levels(f: Features, judgment: str) -> Levels:
    if judgment == "매도":
        return Levels(
            entry_pullback=None,
            entry_breakout=None,
            target=None,
            stop=None,
            support_1=_round_price(f.ichi_base),
            support_2=_round_price(f.cloud_bottom),
            resistance_1=_round_price(f.ichi_conv if (f.ichi_conv or 0) > f.close else f.cloud_top),
            resistance_2=_round_price(f.high_52w),
        )

    # 눌림 진입: 가장 가까운 지지 (ma20, ichi_conv 중 close 아래에서 가장 가까운 것)
    pullback_candidates = [
        v for v in (f.ma20, f.ichi_conv) if v is not None and v <= f.close
    ]
    if pullback_candidates:
        entry_pullback = max(pullback_candidates)
    else:
        # 둘 다 close보다 위 → 더 낮은 것을 선택 (호환성 유지)
        candidates = [v for v in (f.ma20, f.ichi_conv) if v is not None]
        entry_pullback = min(candidates) if candidates else None

    # 돌파 진입: 최근 12주 고가
    entry_breakout = f.high_12w if (f.high_12w is not None and f.high_12w > f.close) else None

    # 목표가: close + 2*atr14, 단 52주 고가가 더 가까우면(작으면) 그것 사용
    if f.atr14 is not None:
        atr_target = f.close + 2 * f.atr14
        if f.high_52w is not None and f.close < f.high_52w < atr_target:
            target = f.high_52w
        else:
            target = atr_target
    else:
        target = f.high_52w

    # 손절: min(ichi_base, close - 1.5*atr14)
    stop_candidates = []
    if f.ichi_base is not None:
        stop_candidates.append(f.ichi_base)
    if f.atr14 is not None:
        stop_candidates.append(f.close - 1.5 * f.atr14)
    stop = min(stop_candidates) if stop_candidates else None

    # Price consistency clamp for 매수/홀드
    entry_high = max(p for p in (entry_pullback, entry_breakout) if p is not None) if any(
        p is not None for p in (entry_pullback, entry_breakout)
    ) else None
    entry_low = min(p for p in (entry_pullback, entry_breakout) if p is not None) if entry_high is not None else None

    # Drop breakout if it exceeds target (parser would reject)
    if entry_breakout is not None and target is not None and entry_breakout > target:
        entry_breakout = None

    # Recompute bounds after dropping breakout
    remaining = [p for p in (entry_pullback, entry_breakout) if p is not None]
    entry_low = min(remaining) if remaining else None
    entry_high = max(remaining) if remaining else None

    # If pullback alone exceeds target, raise target to entry + atr
    if entry_pullback is not None and target is not None and target < entry_pullback:
        target = entry_pullback + (f.atr14 or entry_pullback * 0.05)

    # If stop above entry_low, clamp to entry_low * 0.97
    if stop is not None and entry_low is not None and stop >= entry_low:
        stop = entry_low * 0.97

    # If pullback above close (저항이므로 진입 부적합), drop and fall back to a sub-close level
    if entry_pullback is not None and entry_pullback > f.close:
        entry_pullback = f.close * 0.97 if f.atr14 is None else f.close - f.atr14

    # Ensure at least pullback exists for buy/hold so an outcome is evaluable
    if entry_pullback is None:
        entry_pullback = f.close * 0.97 if f.atr14 is None else f.close - f.atr14

    # Re-clamp stop to remain <= entry_pullback
    if stop is not None and stop >= entry_pullback:
        stop = entry_pullback * 0.97

    return Levels(
        entry_pullback=_round_price(entry_pullback),
        entry_breakout=_round_price(entry_breakout),
        target=_round_price(target),
        stop=_round_price(stop),
        support_1=_round_price(f.ichi_conv if (f.ichi_conv is not None and f.ichi_conv <= f.close) else f.ma20),
        support_2=_round_price(f.ichi_base if (f.ichi_base is not None and f.ichi_base <= f.close) else f.cloud_bottom),
        resistance_1=_round_price(f.ichi_conv if (f.ichi_conv is not None and f.ichi_conv > f.close) else f.cloud_top),
        resistance_2=_round_price(f.high_52w),
    )
