from .models import StockRealtime, KLine
from ..stock.fetcher import _fetch_stocks_realtime, fetch_kline as _stock_kline
from ..futures.fetcher import _fetch_futures_realtime, fetch_futures_kline


async def fetch_realtime(codes: list[str]) -> list[StockRealtime]:
    stock_codes = [c for c in codes if c[:2].lower() != "nf"]
    futures_codes = [c for c in codes if c[:2].lower() == "nf"]

    results: list[StockRealtime] = []

    if stock_codes:
        results.extend(await _fetch_stocks_realtime(stock_codes))
    if futures_codes:
        results.extend(await _fetch_futures_realtime(futures_codes))

    return results


async def fetch_kline(code: str, ktype: str = "day", period: int = 20) -> list[KLine]:
    if code[:2].lower() == "nf":
        return await fetch_futures_kline(code, ktype, period)
    return await _stock_kline(code, ktype, period)
