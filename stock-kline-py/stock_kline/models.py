from dataclasses import dataclass


@dataclass
class KLine:
    date: str
    open: float
    close: float
    high: float
    low: float
    volume: float


@dataclass
class StockRealtime:
    code: str
    name: str
    price: float
    change_pct: float
    prev_close: float
    market: str
    currency: str


@dataclass
class Pattern:
    type: str
    position: str
    meaning: str


@dataclass
class TrendAnalysis:
    trend: str
    strength: str
    price_change: str
    analysis: str
