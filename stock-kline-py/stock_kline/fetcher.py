import asyncio
import re

import httpx

from .models import KLine, StockRealtime

MARKET_CONFIG = {
    "sh": {"type": "A", "name": "上证", "currency": "￥"},
    "sz": {"type": "A", "name": "深证", "currency": "￥"},
    "hk": {"type": "HK", "name": "港股", "currency": "HK$"},
    "us": {"type": "US", "name": "美股", "currency": "$"},
    "nf": {"type": "FUTURES", "name": "期货", "currency": "￥"},
}

# 期货品种映射 nf_XX → Sina 合约代码
FUTURES_SYMBOL_MAP = {
    "RB": "RB0",   # 螺纹钢
    "CU": "CU0",   # 沪铜
    "I":  "I0",    # 铁矿石
    "JM": "JM0",   # 焦煤
    "J":  "J0",    # 焦炭
    "MA": "MA0",   # 甲醇
    "TA": "TA0",   # PTA
    "M":  "M0",    # 豆粕
    "Y":  "Y0",    # 豆油
    "P":  "P0",    # 棕榈油
    "SC": "SC0",   # 原油
    "FU": "FU0",   # 燃油
    "SA": "SA0",   # 纯碱
    "AG": "AG0",   # 白银
    "AU": "AU0",   # 黄金
    "IF": "IF0",   # 沪深300股指
    "IH": "IH0",   # 上证50股指
    "IC": "IC0",   # 中证500股指
    "T":  "T0",    # 十年国债
    "TF": "TF0",   # 五年国债
    "V":  "V0",    # PVC（聚氯乙烯）
}

# nf_XX → AKShare 品种名
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

HEADERS = {
    "Referer": "http://web.ifzq.gtimg.cn/",
    "User-Agent": "Mozilla/5.0",
}

REALTIME_URL = "https://qt.gtimg.cn/q={codes}"
KLINE_A_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},{ktype},,,{period},qfq"
KLINE_HK_URL = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline?_var=kline_{ktype}{code}&param={code},{ktype},,,{period}"

TIMEOUT = 15.0


def get_market_info(code: str) -> dict | None:
    prefix = code[:2].lower()
    return MARKET_CONFIG.get(prefix)


async def fetch_realtime(codes: list[str]) -> list[StockRealtime]:
    stock_codes = [c for c in codes if c[:2].lower() != "nf"]
    futures_codes = [c for c in codes if c[:2].lower() == "nf"]

    results: list[StockRealtime] = []

    if stock_codes:
        results.extend(await _fetch_stocks_realtime(stock_codes))
    if futures_codes:
        results.extend(await _fetch_futures_realtime(futures_codes))

    return results


async def _fetch_stocks_realtime(codes: list[str]) -> list[StockRealtime]:
    codes_str = ",".join(codes)
    url = REALTIME_URL.format(codes=codes_str)

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, headers=HEADERS)
            resp.encoding = "gbk"
            text = resp.text
    except Exception:
        return []

    results: list[StockRealtime] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'v_(.+)="(.+)"', line)
        if not m:
            continue
        code = m.group(1)
        values = m.group(2).split("~")
        if len(values) < 33:
            continue

        name = values[1]
        price = float(values[3]) if values[3] else 0.0
        change_pct = float(values[32]) if values[32] else 0.0
        prev_close = float(values[4]) if values[4] else 0.0
        market_info = get_market_info(code)

        results.append(
            StockRealtime(
                code=code,
                name=name,
                price=price,
                change_pct=change_pct,
                prev_close=prev_close,
                market=market_info["name"] if market_info else "",
                currency=market_info["currency"] if market_info else "",
            )
        )

    return results


def _futures_code_to_sina(code: str) -> str:
    symbol = code[3:].upper()
    if symbol in FUTURES_SYMBOL_MAP:
        return FUTURES_SYMBOL_MAP[symbol]
    return f"{symbol}0"


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


async def fetch_kline(code: str, ktype: str = "day", period: int = 20) -> list[KLine]:
    market_info = get_market_info(code)
    if not market_info:
        raise ValueError(f"不支持的代码格式: {code}")

    if market_info["type"] == "FUTURES":
        return await _futures_kline(code, ktype, period)

    if market_info["type"] == "US":
        raise ValueError("美股暂不支持K线图")

    if market_info["type"] == "HK":
        url = KLINE_HK_URL.format(code=code, ktype=ktype, period=period)
    else:
        url = KLINE_A_URL.format(code=code, ktype=ktype, period=period)

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, headers=HEADERS)
    except Exception as e:
        raise ValueError(f"网络请求失败: {e}")

    data = resp.json() if market_info["type"] == "A" else _parse_hk_response(resp.text)

    stock_data = data.get("data", {}).get(code)
    if not stock_data:
        raise ValueError(f"未能获取到{code}的K线数据")

    klines = stock_data.get(ktype) or stock_data.get(f"qfq{ktype}")
    if not klines:
        raise ValueError(f"未能获取到{code}的{ktype}K线数据")

    return _parse_klines(klines)


async def _futures_kline(code: str, ktype: str, period: int) -> list[KLine]:
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


def _parse_klines(klines: list) -> list[KLine]:
    result = []
    for k in klines:
        result.append(
            KLine(
                date=str(k[0]),
                open=float(k[1]),
                close=float(k[2]),
                high=float(k[3]),
                low=float(k[4]),
                volume=float(k[5]),
            )
        )
    return result


def _parse_hk_response(text: str) -> dict:
    import json
    text = re.sub(r"^[^{]*=", "", text)
    return json.loads(text)
