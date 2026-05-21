import re

import httpx

from .models import KLine, StockRealtime

MARKET_CONFIG = {
    "sh": {"type": "A", "name": "上证", "currency": "￥"},
    "sz": {"type": "A", "name": "深证", "currency": "￥"},
    "hk": {"type": "HK", "name": "港股", "currency": "HK$"},
    "us": {"type": "US", "name": "美股", "currency": "$"},
}

REALTIME_URL = "https://qt.gtimg.cn/q={codes}"
KLINE_A_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},{ktype},,,{period},qfq"
KLINE_HK_URL = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline?_var=kline_{ktype}{code}&param={code},{ktype},,,{period}"

HEADERS = {
    "Referer": "http://web.ifzq.gtimg.cn/",
    "User-Agent": "Mozilla/5.0",
}

TIMEOUT = 15.0


def get_market_info(code: str) -> dict | None:
    prefix = code[:2].lower()
    return MARKET_CONFIG.get(prefix)


async def fetch_realtime(codes: list[str]) -> list[StockRealtime]:
    codes_str = ",".join(codes)
    url = REALTIME_URL.format(codes=codes_str)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, headers=HEADERS)
        resp.encoding = "gbk"
        text = resp.text

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


async def fetch_kline(code: str, ktype: str = "day", period: int = 20) -> list[KLine]:
    market_info = get_market_info(code)
    if not market_info:
        raise ValueError(f"不支持的股票代码格式: {code}")

    if market_info["type"] == "US":
        raise ValueError("美股暂不支持K线图")

    if market_info["type"] == "HK":
        url = KLINE_HK_URL.format(code=code, ktype=ktype, period=period)
    else:
        url = KLINE_A_URL.format(code=code, ktype=ktype, period=period)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, headers=HEADERS)

    data = resp.json() if market_info["type"] == "A" else _parse_hk_response(resp.text)

    stock_data = data.get("data", {}).get(code)
    if not stock_data:
        raise ValueError(f"未能获取到{code}的K线数据")

    klines = stock_data.get(ktype) or stock_data.get(f"qfq{ktype}")
    if not klines:
        raise ValueError(f"未能获取到{code}的{ktype}K线数据")

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
