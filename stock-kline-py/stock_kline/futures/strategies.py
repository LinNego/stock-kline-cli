from abc import ABC, abstractmethod
from importlib import util as _importlib_util
from typing import Any

from ..common.models import KLine


class Strategy(ABC):
    name: str = "base"
    description: str = ""

    @abstractmethod
    def check(self, bars: list[KLine]) -> dict | None:
        ...


# ────────────────── 内置策略 ──────────────────

class BreakoutStrategy(Strategy):
    name = "breakout"
    description = "平台盘整后放量突破 (platform_bars=6, range<0.8%, vol>2.5x)"

    def __init__(self, platform_bars: int = 6, range_pct: float = 0.008, vol_boost: float = 2.5):
        self.platform_bars = platform_bars
        self.range_pct = range_pct
        self.vol_boost = vol_boost

    def check(self, bars: list[KLine]) -> dict | None:
        n = self.platform_bars
        if len(bars) <= n:
            return None

        platform_bars = bars[-n - 1:-1]
        current = bars[-1]

        plat = self._detect_platform(platform_bars)
        if plat is None:
            return None

        vol_burst = current.volume > plat["avg_vol"] * self.vol_boost
        up_break = current.close > plat["high"]
        down_break = current.close < plat["low"]

        if up_break and vol_burst:
            return {
                "strategy": self.name,
                "direction": "up",
                "price": current.close,
                "vol": current.volume,
                "platform_high": plat["high"],
                "platform_low": plat["low"],
                "avg_vol": plat["avg_vol"],
                "vol_ratio": current.volume / plat["avg_vol"] if plat["avg_vol"] else 0,
                "range_pct": plat["range_pct"],
            }

        if down_break and vol_burst:
            return {
                "strategy": self.name,
                "direction": "down",
                "price": current.close,
                "vol": current.volume,
                "platform_high": plat["high"],
                "platform_low": plat["low"],
                "avg_vol": plat["avg_vol"],
                "vol_ratio": current.volume / plat["avg_vol"] if plat["avg_vol"] else 0,
                "range_pct": plat["range_pct"],
            }

        return None

    def _detect_platform(self, bars: list[KLine]) -> dict | None:
        if len(bars) < self.platform_bars:
            return None

        recent = bars[-self.platform_bars:]
        highs = [b.high for b in recent]
        lows = [b.low for b in recent]
        closes = [b.close for b in recent]
        vols = [b.volume for b in recent]

        avg_price = sum(closes) / len(closes)
        price_range = max(highs) - min(lows)
        range_pct = price_range / avg_price if avg_price else 0

        if range_pct > self.range_pct:
            return None

        return {
            "bars": self.platform_bars,
            "high": max(highs),
            "low": min(lows),
            "avg_vol": sum(vols) / len(vols) if vols else 0,
            "range_pct": range_pct,
        }


class MACrossStrategy(Strategy):
    name = "ma_cross"
    description = "MA5上穿/下穿 MA10 (fast=5, slow=10)"

    def __init__(self, fast: int = 5, slow: int = 10):
        self.fast = fast
        self.slow = slow

    def _ma(self, closes: list[float], n: int) -> float:
        if len(closes) < n:
            return 0.0
        return sum(closes[-n:]) / n

    def check(self, bars: list[KLine]) -> dict | None:
        if len(bars) < self.slow + 2:
            return None

        closes = [b.close for b in bars]
        ma_fast_now = self._ma(closes, self.fast)
        ma_slow_now = self._ma(closes, self.slow)
        ma_fast_prev = self._ma(closes[:-1], self.fast)
        ma_slow_prev = self._ma(closes[:-1], self.slow)

        current = bars[-1]

        if ma_fast_prev <= ma_slow_prev and ma_fast_now > ma_slow_now:
            return {
                "strategy": self.name,
                "direction": "up",
                "price": current.close,
                "ma_fast": ma_fast_now,
                "ma_slow": ma_slow_now,
            }

        if ma_fast_prev >= ma_slow_prev and ma_fast_now < ma_slow_now:
            return {
                "strategy": self.name,
                "direction": "down",
                "price": current.close,
                "ma_fast": ma_fast_now,
                "ma_slow": ma_slow_now,
            }

        return None


class VolumeSpikeStrategy(Strategy):
    name = "vol_spike"
    description = "单根放量 (vol > avg_vol * N, 默认 N=3)"

    def __init__(self, lookback: int = 10, spike: float = 3.0):
        self.lookback = lookback
        self.spike = spike

    def check(self, bars: list[KLine]) -> dict | None:
        if len(bars) < self.lookback + 1:
            return None

        current = bars[-1]
        recent = bars[-self.lookback - 1:-1]
        avg_vol = sum(b.volume for b in recent) / len(recent) if recent else 0

        if avg_vol <= 0 or current.volume <= avg_vol * self.spike:
            return None

        direction = "up" if current.close >= current.open else "down"
        return {
            "strategy": self.name,
            "direction": direction,
            "price": current.close,
            "vol": current.volume,
            "avg_vol": avg_vol,
            "vol_ratio": current.volume / avg_vol,
        }


# ────────────────── 注册表 ──────────────────

BUILTIN: dict[str, type[Strategy]] = {
    "breakout": BreakoutStrategy,
    "ma_cross": MACrossStrategy,
    "vol_spike": VolumeSpikeStrategy,
}


def get_strategy(name: str, **kwargs: Any) -> Strategy | None:
    cls = BUILTIN.get(name)
    if cls is None:
        return None
    strategy = cls(**kwargs) if kwargs else cls()
    return strategy


def load_strategy_from_file(filepath: str) -> Strategy | None:
    spec = _importlib_util.spec_from_file_location("custom_strategy", filepath)
    if spec is None or spec.loader is None:
        return None
    mod = _importlib_util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    for attr in dir(mod):
        obj = getattr(mod, attr)
        if isinstance(obj, type) and issubclass(obj, Strategy) and obj is not Strategy:
            return obj()
    return None


def list_strategies() -> list[tuple[str, str]]:
    return [(name, cls().description) for name, cls in BUILTIN.items()]
