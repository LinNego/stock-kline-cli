import asyncio
import sys
from datetime import datetime
from io import StringIO

from rich.console import Console as RichConsole

from ..common.models import KLine
from ..common.chart_ascii import plot_kline, render_volume
from ..common.theme import THEMES
from .fetcher import FUTURES_SYMBOL_MAP, NF_TO_AKSHARE
from .strategies import Strategy, get_strategy, BreakoutStrategy

BELL = "\a"

DISGUISE_TITLES = [
    "gcc -O2 -c main.c",
    "cc1plus -quiet -O2 main.cpp -o main.o",
    "python3 setup.py build_ext --inplace",
    "make -j4 all",
    "npm install --save-dev typescript",
    "apt-get install -y libssl-dev",
    "systemd-journald[548]: 5 entries suppressed",
    "journalctl -u sshd -n 50",
    "git fetch origin --prune",
    "git rebase -i HEAD~3",
    "python3 -m pip install --user pytest",
    "cargo build --release",
    "docker-compose up -d postgres",
    "sshd[1624]: Accepted publickey for root",
    "systemd[1]: Starting Network Manager...",
]


def _set_title(title: str) -> None:
    sys.stdout.write(f"\033]0;{title}\007")
    sys.stdout.flush()


def _cycle_title(tick: int) -> None:
    title = DISGUISE_TITLES[tick % len(DISGUISE_TITLES)]
    _set_title(title)


def _next_boundary(dt: datetime, interval: int) -> datetime:
    minutes = dt.minute
    next_min = ((minutes // interval) + 1) * interval
    if next_min >= 60:
        next_dt = dt.replace(hour=dt.hour + 1, minute=0, second=0, microsecond=0)
    else:
        next_dt = dt.replace(minute=next_min, second=0, microsecond=0)
    return next_dt


def _load_historical_bars(code: str, interval: int, max_bars: int) -> list[KLine]:
    import akshare as ak

    symbol = code[3:].upper()
    sina_code = FUTURES_SYMBOL_MAP.get(symbol)
    if not sina_code:
        return []

    akshare_symbol = NF_TO_AKSHARE.get(symbol)
    if not akshare_symbol:
        return []

    try:
        df = ak.futures_zh_minute_sina(symbol=sina_code, period=str(interval))
    except Exception:
        return []

    bars = []
    for _, row in df.iterrows():
        dt = str(row['datetime'])
        time_str = dt[-8:-3] if len(dt) >= 16 else dt[-5:]
        bars.append(KLine(
            date=time_str,
            open=float(row['open']),
            close=float(row['close']),
            high=float(row['high']),
            low=float(row['low']),
            volume=float(row['volume']),
        ))

    if not bars:
        return []
    now = datetime.now()
    last_bar_time = bars[-1].date
    try:
        parts = last_bar_time.split(":")
        last_h, last_m = int(parts[0]), int(parts[1])
        now_h, now_m = now.hour, now.minute
        last_total = last_h * 60 + last_m
        now_total = now_h * 60 + now_m
        if last_total > now_total:
            last_total -= 1440
        if now_total - last_total > interval * 3:
            return []
    except (ValueError, IndexError):
        pass

    seg = [bars[-1]]
    for b in reversed(bars[:-1]):
        gap = _bar_time_diff(b, seg[0])
        if gap > interval * 30:
            break
        seg.insert(0, b)

    return seg[-max_bars:] if len(seg) > max_bars else seg


def _bar_time_diff(a: KLine, b: KLine) -> int:
    def _to_min(t: str) -> int:
        parts = t.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    diff = _to_min(b.date) - _to_min(a.date)
    if diff < 0:
        diff += 1440
    return diff


def _get_last_bar_time(bars: list[KLine]) -> datetime | None:
    if not bars:
        return None
    t = bars[-1].date
    parts = t.split(":")
    if len(parts) == 2:
        now = datetime.now()
        return now.replace(hour=int(parts[0]), minute=int(parts[1]), second=0, microsecond=0)
    return None


def _refetch_bars(code: str, interval: int, max_bars: int) -> list[KLine]:
    return _load_historical_bars(code, interval, max_bars)


def _render_display(
    bars: list[KLine],
    code: str,
    name: str,
    interval: int,
    chart_height: int,
    theme,
    next_boundary_time: datetime | None = None,
    signal: dict | None = None,
    stealth: bool = False,
) -> str:
    buf = StringIO()

    if stealth:
        if bars:
            all_prices = [p for b in bars for p in (b.high, b.low, b.open, b.close)]
            vmin = min(all_prices)
            vmax = max(all_prices)
            span = vmax - vmin or 1
            close = bars[-1].close
            close_is_up = bars[-1].close >= bars[-1].open
            high_ansi = f"\033[{theme.up_ansi}m"
            low_ansi = f"\033[{theme.down_ansi}m"
            close_ansi = f"\033[{theme.up_ansi if close_is_up else theme.down_ansi}m"
            reset = "\033[0m"

            def _row_of(p):
                return int((p - vmin) / span * (chart_height - 1))

            row_h = _row_of(vmax)
            row_l = _row_of(vmin)
            row_c = _row_of(close)

            labels: dict[int, tuple[str, str]] = {}
            if row_c >= 0:
                labels[row_c] = (close_ansi, f"{close:>7.2f}")
            if row_h >= 0 and row_h not in labels:
                labels[row_h] = (high_ansi, f"H {vmax:>5.0f}")
            if row_l >= 0 and row_l not in labels:
                labels[row_l] = (low_ansi, f"L {vmin:>5.0f}")

            chart = plot_kline(bars, height=chart_height, theme=theme)
            chart_lines = chart.split("\n")

            for i, line in enumerate(chart_lines):
                i_rev = chart_height - 1 - i
                lbl = labels.get(i_rev)
                if lbl:
                    ansi, text = lbl
                    buf.write(f"{ansi}{text}{reset}   ")
                else:
                    buf.write(" " * 10)
                buf.write(line + "\n")

            vol = render_volume(bars, width=40, theme=theme, compact=True)
            if vol:
                buf.write(" " * 10 + vol + "\n")
        if next_boundary_time:
            remaining = (next_boundary_time - datetime.now()).total_seconds()
            if remaining > 0:
                buf.write(f"\033[90m{next_boundary_time.strftime('%H:%M')} {int(remaining)}s\033[0m\n")
        return buf.getvalue()

    c = RichConsole(file=buf, force_terminal=True, width=120)

    c.print(f"[bold]{name} ({code})  {interval}分钟K线  已采集{len(bars)}根[/bold]")

    if bars:
        chart = plot_kline(bars, height=chart_height, theme=theme)
        buf.write(chart + "\n")
        vol = render_volume(bars, width=40, theme=theme)
        if vol:
            buf.write(vol + "\n")

        high_bar = max(bars, key=lambda x: x.high)
        low_bar = min(bars, key=lambda x: x.low)
        change = ((bars[-1].close - bars[0].open) / bars[0].open * 100) if bars[0].open else 0
        c.print(
            f"[dim]区间: 最高 {high_bar.high:.2f}  最低 {low_bar.low:.2f}  "
            f"涨跌 {change:+.2f}%  共{len(bars)}根[/dim]"
            f"  [dim]最新 {bars[-1].close:.2f}[/dim]"
        )

    c.print()

    if signal:
        d = signal["direction"]
        icon = "▲" if d == "up" else "▼"
        color = "red" if d == "up" else "green"
        c.print(
            f"[bold {color}]{BELL} {icon} 信号: {d.upper()}放量突破! "
            f"价格={signal['price']:.2f}  量比={signal['vol_ratio']:.1f}x  "
            f"平台区间[{signal['platform_low']:.2f}-{signal['platform_high']:.2f}]"
            f"[/bold {color}]"
        )

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
    enable_signal: bool = False,
    stealth: bool = False,
    strategy: Strategy | None = None,
    disguise: bool = False,
) -> None:
    from rich.console import Console
    console = Console()
    theme = THEMES["stealth" if stealth else "subtle"]
    signal: dict | None = None

    bars = _load_historical_bars(code, interval, max_bars)
    if not bars:
        if not stealth:
            console.print("[yellow]当前非交易时段[/yellow]")
        while not bars:
            await asyncio.sleep(30)
            bars = _load_historical_bars(code, interval, max_bars)
    if bars and not stealth:
        console.print(f"[dim]已加载 {len(bars)} 根历史K线[/dim]")

    name = code
    symbol = code[3:].upper()
    aks_name = NF_TO_AKSHARE.get(symbol, symbol)
    now = datetime.now()
    next_boundary = _next_boundary(now, interval)

    output = _render_display(
        bars, code, aks_name, interval,
        chart_height, theme, next_boundary, signal,
        stealth=stealth,
    )
    sys.stdout.write(output)
    sys.stdout.flush()
    prev_lines = output.rstrip("\n").count("\n") + 1
    disguise_tick = 0
    if disguise:
        _set_title(DISGUISE_TITLES[0])

    try:
        while True:
            remaining = (next_boundary - datetime.now()).total_seconds()
            if remaining > 3:
                await asyncio.sleep(3)
                if disguise:
                    disguise_tick += 1
                    _cycle_title(disguise_tick)
                output = _render_display(
                    bars, code, aks_name, interval,
                    chart_height, theme, next_boundary, signal,
                    stealth=stealth,
                )
                lines = output.rstrip("\n").count("\n") + 1
                sys.stdout.write(f"\033[{prev_lines}A\033[J{output}")
                sys.stdout.flush()
                prev_lines = lines
                continue

            if remaining > 0:
                await asyncio.sleep(remaining)

            new_bars = _refetch_bars(code, interval, max_bars)
            if new_bars:
                bars = new_bars
                if enable_signal and strategy:
                    signal = strategy.check(bars)
                    if signal:
                        sys.stdout.write(BELL)
                        sys.stdout.flush()

            now = datetime.now()
            next_boundary = _next_boundary(now, interval)

            output = _render_display(
                bars, code, aks_name, interval,
                chart_height, theme, next_boundary, signal,
                stealth=stealth,
            )
            lines = output.rstrip("\n").count("\n") + 1
            sys.stdout.write(f"\033[{prev_lines}A\033[J{output}")
            sys.stdout.flush()
            prev_lines = lines

    except KeyboardInterrupt:
        print()
        if not stealth:
            console.print("[yellow]K线采集已停止[/yellow]")


async def run_replay(
    codes: list[str],
    interval: int = 5,
    max_bars: int = 40,
    chart_height: int = 12,
    speed: float = 0.3,
    enable_signal: bool = True,
    stealth: bool = False,
    strategy: Strategy | None = None,
    disguise: bool = False,
) -> None:
    from rich.console import Console
    console = Console()
    theme = THEMES["stealth" if stealth else "subtle"]

    all_hist = {}
    for code in codes:
        bars = _load_historical_bars(code, interval, 9999)
        if bars:
            all_hist[code] = bars

    if not all_hist:
        console.print("[red]无历史数据[/red]")
        return

    idx: dict[str, int] = {c: 7 for c in all_hist}
    signal_log: list[tuple[str, dict]] = []
    first = True
    prev_lines = 0
    disguise_tick = 0
    if disguise:
        _set_title(DISGUISE_TITLES[0])
        console.print(f"[dim]伪装模式[/dim]")

    console.print(f"[dim]回测模式  {len(all_hist)}品种  每个品种{sum(len(v) for v in all_hist.values())}根 bar[/dim]")
    console.print(f"[dim]速度={speed}s/bar  Ctrl+C退出[/dim]\n")

    try:
        while any(idx[c] < len(all_hist[c]) for c in all_hist):
            if disguise:
                disguise_tick += 1
                _cycle_title(disguise_tick)
            output_parts = []

            for code in codes:
                bars = all_hist.get(code, [])
                if not bars or idx.get(code, 0) >= len(bars):
                    if not stealth:
                        symbol = code[3:].upper()
                        aks_name = NF_TO_AKSHARE.get(symbol, symbol)
                        buf = StringIO()
                        c = RichConsole(file=buf, force_terminal=True, width=120)
                        c.print(f"[dim]{aks_name} ({code})  回测完成[/dim]")
                        output_parts.append(buf.getvalue().rstrip("\n"))
                    continue

                i = idx[code]
                window = bars[max(0, i - max_bars + 1):i + 1]

                symbol = code[3:].upper()
                aks_name = NF_TO_AKSHARE.get(symbol, symbol)
                signal = None
                if enable_signal and strategy:
                    signal = strategy.check(window)
                    if signal:
                        label = bars[i].date if i < len(bars) else ""
                        signal_log.append((code, {**signal, "bar_time": label}))
                        if not stealth:
                            sys.stdout.write(BELL)
                            sys.stdout.flush()

                            symbol = code[3:].upper()
                            aks_name = NF_TO_AKSHARE.get(symbol, symbol)
                            d = signal["direction"]
                            icon = "▲" if d == "up" else "▼"
                            color = "red" if d == "up" else "green"

                            sig_buf = StringIO()
                            sc = RichConsole(file=sig_buf, force_terminal=True, width=120)
                            sc.print(f"\n[bold {color}]{icon} 信号 #{len(signal_log)}: {aks_name} {label} {d} {signal.get('strategy','?')}[/bold {color}]")
                            parts = [f"价格={signal.get('price', 0):.2f}"]
                            if signal.get('vol_ratio'):
                                parts.append(f"量比={signal['vol_ratio']:.1f}x")
                                parts.append(f"平台[{signal.get('platform_low', 0):.2f}-{signal.get('platform_high', 0):.2f}]")
                            if signal.get('ma_fast'):
                                parts.append(f"MA{signal.get('ma_fast',0):.0f}/{signal.get('ma_slow',0):.0f}")
                            sc.print(f"[{color}]{'  '.join(parts)}[/{color}]")
                            sc.print(f"[dim]────────────────────────────────[/dim]")
                            chart = plot_kline(window, height=chart_height, theme=theme)
                            sig_buf.write(chart + "\n")
                            vol = render_volume(window, width=40, theme=theme)
                            if vol:
                                sig_buf.write(vol + "\n")
                            sc.print(f"[dim]按任意键继续...[/dim]")

                            sys.stdout.write(f"\033[{prev_lines}A\033[J")
                            sys.stdout.write("".join(output_parts) + "\n" + sig_buf.getvalue())
                            sys.stdout.flush()

                            try:
                                import termios, tty
                                fd = sys.stdin.fileno()
                                old = termios.tcgetattr(fd)
                                tty.setraw(fd)
                                sys.stdin.read(1)
                                termios.tcsetattr(fd, termios.TCSADRAIN, old)
                            except Exception:
                                await asyncio.sleep(2)

                            sys.stdout.write(f"\033[{prev_lines}A\033[J")
                            sys.stdout.flush()
                            prev_lines = 0
                            first = True

                output = _render_display(
                    window, code, aks_name, interval,
                    chart_height, theme, None, signal,
                    stealth=stealth,
                )
                if not stealth:
                    bar_info = f"[dim]{bars[i].date} O={bars[i].open} C={bars[i].close} V={bars[i].volume:.0f}[/dim]"
                    output_parts.append(output.rstrip("\n") + "\n" + bar_info)
                else:
                    output_parts.append(output.rstrip("\n"))

                idx[code] += 1

            full = "\n\n".join(output_parts)

            if first:
                sys.stdout.write(full + "\n")
                sys.stdout.flush()
                prev_lines = full.rstrip("\n").count("\n") + 1
                first = False
            else:
                sys.stdout.write(f"\033[{prev_lines}A\033[J{full}\n")
                sys.stdout.flush()
                prev_lines = full.rstrip("\n").count("\n") + 1

            await asyncio.sleep(speed)

    except KeyboardInterrupt:
        pass

    print()
    if signal_log and not stealth:
        console.print(f"\n[bold]信号汇总 ({len(signal_log)}次):[/bold]")
        for scode, s in signal_log:
            d = s["direction"]
            icon = "▲" if d == "up" else "▼"
            color = "red" if d == "up" else "green"
            detail = ""
            if s.get("vol_ratio"):
                detail = f"量比={s['vol_ratio']:.1f}x 平台[{s.get('platform_low',0):.1f}-{s.get('platform_high',0):.1f}]"
            elif s.get("ma_fast"):
                detail = f"MA{s.get('ma_fast',0):.0f}/{s.get('ma_slow',0):.0f}"
            console.print(
                f"  [{color}]{icon} {scode} {s.get('bar_time','')} {s.get('strategy','')}"
                f"  价格={s['price']:.2f}  {detail}"
                f"[/{color}]"
            )

    console.print("[yellow]回测完成[/yellow]")
