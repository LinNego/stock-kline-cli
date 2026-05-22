import asyncio
import sys
from datetime import datetime, timedelta
from io import StringIO

from rich.console import Console as RichConsole

from .fetcher import fetch_realtime
from .models import KLine
from .chart_ascii import plot_kline, render_volume
from .theme import THEMES


def _next_boundary(dt: datetime, interval: int) -> datetime:
    minutes = dt.minute
    next_min = ((minutes // interval) + 1) * interval
    if next_min >= 60:
        next_dt = dt.replace(hour=dt.hour + 1, minute=0, second=0, microsecond=0)
    else:
        next_dt = dt.replace(minute=next_min, second=0, microsecond=0)
    return next_dt


def _render_display(
    bars: list[KLine],
    current_ohlc: dict | None,
    code: str,
    name: str,
    interval: int,
    chart_height: int,
    theme,
    next_boundary_time: datetime | None = None,
) -> str:
    buf = StringIO()
    c = RichConsole(file=buf, force_terminal=True, width=120)

    c.print(f"[bold]{name} ({code})  {interval}分钟K线  已采集{len(bars)}根[/bold]")

    if bars:
        chart = plot_kline(bars, height=chart_height, theme=theme)
        c.print(chart)
        vol = render_volume(bars, width=40, theme=theme)
        if vol:
            c.print(f"[dim]{vol}[/dim]")

        high_bar = max(bars, key=lambda x: x.high)
        low_bar = min(bars, key=lambda x: x.low)
        change = ((bars[-1].close - bars[0].open) / bars[0].open * 100) if bars[0].open else 0
        c.print(
            f"[dim]区间: 最高 {high_bar.high:.2f}  最低 {low_bar.low:.2f}  "
            f"涨跌 {change:+.2f}%  共{len(bars)}根[/dim]"
        )

    c.print()

    if current_ohlc:
        line = (
            f"[bold]当前K线:[/bold] "
            f"O:[cyan]{current_ohlc['open']:.2f}[/cyan] "
            f"H:[green]{current_ohlc['high']:.2f}[/green] "
            f"L:[red]{current_ohlc['low']:.2f}[/red] "
            f"C:[yellow]{current_ohlc['close']:.2f}[/yellow]"
        )
        c.print(line)

    if next_boundary_time:
        remaining = (next_boundary_time - datetime.now()).total_seconds()
        if remaining > 0:
            c.print(f"下次更新: {next_boundary_time.strftime('%H:%M:%S')}  (剩余{remaining:.0f}s)")

    return buf.getvalue()


async def run_realtime_kline(
    code: str,
    interval: int = 5,
    max_bars: int = 40,
    chart_height: int = 12,
    proxy: str | None = None,
) -> None:
    from rich.console import Console
    console = Console()
    theme = THEMES["subtle"]

    now = datetime.now()
    next_boundary = _next_boundary(now, interval)
    wait_seconds = (next_boundary - now).total_seconds()

    if wait_seconds > 1:
        console.print(
            f"同步至 {next_boundary.strftime('%H:%M:%S')}（等待{wait_seconds:.0f}s）..."
        )
        await asyncio.sleep(wait_seconds)

    bars: list[KLine] = []
    current_ohlc: dict | None = None
    prev_lines = 0
    first = True
    stock_name = code

    try:
        while True:
            now = datetime.now()
            next_boundary = _next_boundary(now, interval)

            stocks = await fetch_realtime([code])
            if not stocks:
                await asyncio.sleep(3)
                continue

            stock = stocks[0]
            stock_name = stock.name
            price = stock.price

            if current_ohlc is None:
                current_ohlc = {
                    "open": price, "high": price, "low": price, "close": price,
                    "start_time": now,
                }
            else:
                if price > current_ohlc["high"]:
                    current_ohlc["high"] = price
                if price < current_ohlc["low"]:
                    current_ohlc["low"] = price
                current_ohlc["close"] = price

            if now >= next_boundary:
                if current_ohlc:
                    bar = KLine(
                        date=current_ohlc["start_time"].strftime("%H:%M"),
                        open=current_ohlc["open"],
                        close=price,
                        high=current_ohlc["high"],
                        low=current_ohlc["low"],
                        volume=0,
                    )
                    bars.append(bar)
                    if len(bars) > max_bars:
                        bars.pop(0)

                current_ohlc = {
                    "open": price, "high": price, "low": price, "close": price,
                    "start_time": now,
                }

            output = _render_display(
                bars, current_ohlc, code, stock_name, interval,
                chart_height, theme, next_boundary,
            )

            current_lines = output.rstrip("\n").count("\n") + 1
            if first:
                sys.stdout.write(output)
                sys.stdout.flush()
                prev_lines = current_lines
                first = False
            else:
                sys.stdout.write(f"\033[{prev_lines}A\033[J{output}")
                sys.stdout.flush()
                prev_lines = current_lines

            await asyncio.sleep(3)

    except KeyboardInterrupt:
        print()
        console.print("[yellow]K线采集已停止[/yellow]")
