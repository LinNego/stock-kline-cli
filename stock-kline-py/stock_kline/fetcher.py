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


def _futures_code_to_sina(code: str) -> str:
    symbol = code[3:].upper()
    if symbol in FUTURES_SYMBOL_MAP:
        return FUTURES_SYMBOL_MAP[symbol]
    return f"{symbol}0"


def _futures_symbol_to_kline(code: str) -> str:
    symbol = code[3:].upper()
    return FUTURES_SYMBOL_MAP.get(symbol, f"{symbol}0")


async def _fetch_futures_realtime(codes: list[str]) -> list[StockRealtime]:
    sina_codes = [_futures_code_to_sina(c) for c in codes]
    url = f"https://hq.sinajs.cn/list={','.join(sina_codes)}"
    sina_headers = {
        "Referer": "https://finance.sina.com.cn",
        "User-Agent": "Mozilla/5.0",
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, headers=sina_headers)
        resp.encoding = "gbk"
        text = resp.text

    results: list[StockRealtime] = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or "hq_str_" not in line:
            continue
        m = re.match(r'var hq_str_\w+="(.+)"', line)
        if not m:
            continue
        values = m.group(1).split(",")
        if len(values) < 10:
            continue

        name = values[0]
        prev_close = float(values[3]) if values[3] else 0.0
        current_price = float(values[4]) if values[4] else 0.0
        change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0.0
        idx = len(results)
        code = codes[idx] if idx < len(codes) else ""

        results.append(
            StockRealtime(
                code=code,
                name=name,
                price=current_price,
                change_pct=change_pct,
                prev_close=prev_close,
                market="期货",
                currency="￥",
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

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, headers=HEADERS)

    data = resp.json() if market_info["type"] == "A" else _parse_hk_response(resp.text)

    stock_data = data.get("data", {}).get(code)
    if not stock_data:
        raise ValueError(f"未能获取到{code}的K线数据")

    klines = stock_data.get(ktype) or stock_data.get(f"qfq{ktype}")
    if not klines:
        raise ValueError(f"未能获取到{code}的{ktype}K线数据")

    return _parse_klines(klines)


async def _futures_kline(code: str, ktype: str, period: int) -> list[KLine]:
    symbol = _futures_symbol_to_kline(code)

    if ktype.startswith("m"):
        raise ValueError(f"期货暂不支持分钟K线（{ktype}），请使用 day/week 查看日K/周K")

    url = "https://stock.finance.sina.com.cn/futures/api/json_v2.php/IndexService.getInnerFuturesDailyKLine"
    params = {"symbol": symbol}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, params=params)

    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(f"未能获取到{code}的K线数据")

    return _parse_klines(data[-period:] if len(data) > period else data)


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
