from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import KLine
from .theme import ColorTheme, THEMES


def build_kline_panel(
    kline_data: list[KLine],
    stock_name: str,
    code: str,
    ktype: str,
    height: int = 15,
    theme: ColorTheme | None = None,
) -> Panel:
    if theme is None:
        theme = THEMES["subtle"]

    if not kline_data:
        return Panel("暂无数据", title=f"{stock_name}({code})")

    closes = [k.close for k in kline_data]
    highs = [k.high for k in kline_data]
    lows = [k.low for k in kline_data]

    vmin = min(lows)
    vmax = max(highs)
    span = vmax - vmin if vmax != vmin else 1

    rows = []
    for row in range(height):
        threshold = vmax - (span * row / height)
        line_text = Text()
        for i in range(len(closes)):
            if highs[i] >= threshold >= lows[i]:
                is_up = closes[i] >= kline_data[i].open
                char = "┃" if not (i > 0 and row > 0 and row < height - 1) else "│"
                line_text.append(char, style=theme.up_rich if is_up else theme.down_rich)
            else:
                line_text.append(" ")
        rows.append(line_text)

    chart_lines = Text("\n").join(rows)
    panel = Panel(
        chart_lines,
        title=f"{stock_name}({code}) {ktype}K线图 ({len(kline_data)}个周期)",
        box=box.ROUNDED,
    )
    return panel


def build_volume_panel(kline_data: list[KLine], width: int = 40, theme: ColorTheme | None = None) -> Panel:
    if theme is None:
        theme = THEMES["subtle"]

    if not kline_data:
        return Panel("暂无数据", title="成交量")

    volumes = [k.volume for k in kline_data]
    vol_max = max(volumes)
    if vol_max == 0:
        return Panel("无成交量数据", title="成交量")

    block_chars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
    n = len(volumes)
    step = max(1, n // width)
    vol_text = Text()
    for i in range(0, n, step):
        v = volumes[i]
        ratio = v / vol_max
        idx = min(len(block_chars) - 1, int(ratio * len(block_chars)))
        is_up = kline_data[i].close >= kline_data[i].open
        vol_text.append(block_chars[idx], style=theme.up_rich if is_up else theme.down_rich)

    vol_avg = sum(volumes) / n
    max_v_str = f"{vol_max / 100000000:.2f}亿"
    avg_v_str = f"{vol_avg / 100000000:.2f}亿"
    vol_text.append(f"  量: 最高{max_v_str} 均{avg_v_str}")

    return Panel(vol_text, title="成交量", box=box.SIMPLE)


def build_stat_table(kline_data: list[KLine]) -> Table:
    closes = [k.close for k in kline_data]
    highs = [k.high for k in kline_data]
    lows = [k.low for k in kline_data]
    dates = [k.date for k in kline_data]

    price_change = ((closes[-1] - closes[0]) / closes[0] * 100) if closes[0] else 0.0

    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("指标", style="cyan")
    table.add_column("值", style="white")
    table.add_row("时间范围", f"{dates[0]} 至 {dates[-1]}")
    table.add_row("最高", f"{max(highs):.2f}")
    table.add_row("最低", f"{min(lows):.2f}")
    table.add_row("平均", f"{sum(closes)/len(closes):.2f}")
    table.add_row("区间涨跌", f"{price_change:.2f}%")
    return table
