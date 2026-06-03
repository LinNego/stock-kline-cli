from .models import KLine, Pattern, TrendAnalysis


def analyze_kline_pattern(kline_data: list[KLine]) -> list[Pattern]:
    if len(kline_data) < 3:
        return []

    patterns: list[Pattern] = []
    recent = kline_data[-3:]

    last = recent[2]
    body_length = abs(last.close - last.open)
    shadow_length = last.high - last.low
    lower_shadow = min(last.open, last.close) - last.low

    if body_length > 0 and lower_shadow > body_length * 2 and shadow_length > body_length * 3:
        patterns.append(
            Pattern(
                type="锤子线",
                position=last.date,
                meaning="可能预示着下跌趋势即将结束，市场可能反转向上",
            )
        )

    if len(recent) == 3:
        day1, day2, day3 = recent
        day1_body = day1.close - day1.open
        day2_body = abs(day2.close - day2.open)
        day3_body = day3.close - day3.open

        if (
            day1_body < 0
            and day2_body < abs(day1_body) * 0.3
            and day3_body > 0
            and day2.high < day1.close
            and day3.open > day2.high
        ):
            patterns.append(
                Pattern(
                    type="启明星",
                    position=day3.date,
                    meaning="强势反转信号，预示着可能开始上涨趋势",
                )
            )

    return patterns


def analyze_trend(kline_data: list[KLine]) -> TrendAnalysis | None:
    if len(kline_data) < 5:
        return None

    prices = [k.close for k in kline_data]
    ma5 = sum(prices[-5:]) / 5
    ma10 = sum(prices[-10:]) / 10 if len(kline_data) >= 10 else None

    last_price = prices[-1]
    start_price = prices[0]
    price_change = ((last_price - start_price) / start_price * 100) if start_price else 0.0

    if last_price > ma5 and (ma10 is None or ma5 > ma10):
        trend = "上涨"
        strength = "强势" if price_change > 5 else "弱势"
    elif last_price < ma5 and (ma10 is None or ma5 < ma10):
        trend = "下跌"
        strength = "强势" if price_change < -5 else "弱势"
    else:
        trend = "盘整"
        strength = "震荡"

    if trend == "盘整":
        suggestion = "建议观望"
    elif trend == "上涨":
        suggestion = "注意防守" if strength == "强势" else "可以跟进"
    else:
        suggestion = "注意止损" if strength == "强势" else "等待企稳"

    return TrendAnalysis(
        trend=trend,
        strength=strength,
        price_change=f"{price_change:.2f}%",
        analysis=f"{strength}{trend}趋势，区间涨跌幅{price_change:.2f}%，{suggestion}",
    )
