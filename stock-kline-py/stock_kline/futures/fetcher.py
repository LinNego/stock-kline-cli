import asyncio

from ..common.models import KLine, StockRealtime

FUTURES_SYMBOL_MAP = {
    "RB": "RB0", "CU": "CU0", "I": "I0",
    "JM": "JM0", "J": "J0", "MA": "MA0",
    "TA": "TA0", "M": "M0", "Y": "Y0",
    "P": "P0", "SC": "SC0", "FU": "FU0",
    "SA": "SA0", "AG": "AG0", "AU": "AU0",
    "IF": "IF0", "IH": "IH0", "IC": "IC0",
    "T": "T0", "TF": "TF0", "V": "V0",
}

NF_TO_AKSHARE = {
    "RB": "螺纹钢", "CU": "沪铜", "I": "铁矿石",
    "JM": "焦煤", "J": "焦炭", "MA": "郑醇",
    "TA": "PTA", "M": "豆粕", "Y": "豆油",
    "P": "棕榈", "SC": "原油", "FU": "燃油",
    "SA": "纯碱", "AG": "白银", "AU": "黄金",
    "IF": "沪深300指数期货", "IH": "上证50指数期货",
    "IC": "中证500指数期货",
    "T": "10年期国债期货", "TF": "5年期国债期货",
    "V": "PVC",
}


def _futures_symbol_to_kline(code: str) -> str:
    symbol = code[3:].upper()
    return FUTURES_SYMBOL_MAP.get(symbol, f"{symbol}0")


async def _fetch_futures_realtime(codes: list[str]) -> list[StockRealtime]:
    import akshare as ak

    variety_groups: dict[str, list[str]] = {}
    for code in codes:
        symbol = code[3:].upper()
        akshare_symbol = NF_TO_AKSHARE.get(symbol)
        if not akshare_symbol:
            continue
        variety_groups.setdefault(akshare_symbol, []).append(code)

    results: list[StockRealtime] = []

    for akshare_symbol, group_codes in variety_groups.items():
        try:
            df = await asyncio.to_thread(ak.futures_zh_realtime, symbol=akshare_symbol)
        except Exception:
            continue

        for code in group_codes:
            symbol = code[3:].upper()
            sina_code = FUTURES_SYMBOL_MAP.get(symbol, f"{symbol}0")
            match = df[df['symbol'] == sina_code]
            if match.empty and not df.empty:
                match = df.iloc[[0]]
            if match.empty:
                continue

            row = match.iloc[0]
            results.append(
                StockRealtime(
                    code=code,
                    name=row.get('name', akshare_symbol),
                    price=float(row['trade']) if row['trade'] else 0.0,
                    change_pct=float(row['changepercent']) * 100 if row['changepercent'] else 0.0,
                    prev_close=float(row['preclose']) if row['preclose'] else 0.0,
                    market="期货",
                    currency="￥",
                    volume=float(row['volume']) if row['volume'] else 0.0,
                )
            )

    return results


async def fetch_futures_kline(code: str, ktype: str = "day", period: int = 20) -> list[KLine]:
    import akshare as ak

    symbol = _futures_symbol_to_kline(code)
    if ktype.startswith("m"):
        raise ValueError(f"期货暂不支持分钟K线（{ktype}），请使用 day/week 查看日K/周K")

    try:
        df = await asyncio.to_thread(ak.futures_zh_daily_sina, symbol=symbol)
    except Exception as e:
        raise ValueError(f"未能获取到{code}的K线数据: {e}")

    klines = []
    for _, row in df.iterrows():
        klines.append(
            KLine(
                date=str(row['date']),
                open=float(row['open']),
                close=float(row['close']),
                high=float(row['high']),
                low=float(row['low']),
                volume=float(row['volume']),
            )
        )

    return klines[-period:] if len(klines) > period else klines
