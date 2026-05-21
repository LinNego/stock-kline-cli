import argparse
import asyncio
import json
import sys

from rich.console import Console
from rich import box
from rich.table import Table
from rich.panel import Panel

from .analysis import analyze_kline_pattern, analyze_trend
from .chart_ascii import plot_kline as plot_ascii_kline, render_volume as render_ascii_volume
from .chart_rich import build_kline_panel, build_stat_table, build_volume_panel
from .display import print_realtime_table
from .fetcher import fetch_realtime, fetch_kline, get_market_info
from .theme import THEMES
from .search import SEARCH_BACKENDS

console = Console()


def build_analyze_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-kline analyze",
        description="AI深度分析个股（调用LLM生成跟踪分析报告）",
    )
    p.add_argument("stock_code", help="股票代码, 如 sh600000")
    p.add_argument("--prompt", help="prompt模板文件路径（不指定则使用内置默认模板）", type=str)
    p.add_argument(
        "--search-backend",
        help="搜索后端: auto(自动) / tavily(需TAVILY_API_KEY)",
        choices=list(SEARCH_BACKENDS.keys()),
        default="auto",
    )
    p.add_argument(
        "--search-timeout",
        help="每个搜索的超时秒数，默认8",
        type=int,
        default=8,
    )
    p.add_argument(
        "--search-mode",
        help="搜索模式: parallel(并行5次,费credit) / single(合并1次,省credit)",
        choices=["parallel", "single"],
        default="parallel",
    )
    p.add_argument(
        "--no-search",
        help="跳过联网搜索，仅基于股票基础数据进行分析",
        action="store_true",
    )
    p.add_argument(
        "--proxy",
        help="HTTP代理地址，如 http://172.24.160.1:7897（默认从 HTTP_PROXY 环境变量读取）",
        type=str,
    )
    p.add_argument("--ai-model", help="LLM模型名", type=str, default="gpt-4o")
    p.add_argument("--ai-base-url", help="LLM API地址", type=str, default="https://api.openai.com/v1")
    p.add_argument("--ai-api-key", help="API Key（默认从 STOCK_KLINE_API_KEY 环境变量读取）", type=str)
    return p


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock-kline",
        description="在终端上打印股票实时数据和K线图的命令行工具",
    )
    parser.add_argument("-v", "--version", action="version", version="1.0.0")
    parser.add_argument(
        "-s", "--stock",
        help="设置stock代码, 多个以逗号隔开\nA股示例: sh600000,sz000001\n港股示例: hk00700\n美股示例: usAAPL",
        type=lambda s: [x.strip() for x in s.split(",")],
    )
    parser.add_argument(
        "-c", "--config",
        help="设置配置文件路径",
        type=str,
    )
    parser.add_argument("-d", dest="show_head", action="store_false", help="隐藏表头")
    parser.add_argument("--day", action="store_true", help="显示日K数据")
    parser.add_argument("--week", action="store_true", help="显示周K数据")
    parser.add_argument(
        "-p", "--period",
        help="设置显示的周期数量，默认40",
        type=int,
        default=40,
    )
    parser.add_argument(
        "--height",
        help="设置图表高度，默认15",
        type=int,
        default=15,
    )
    parser.add_argument("--ai", action="store_true", help="开启AI分析")
    parser.add_argument(
        "--chart-type",
        help="图表展示方式 (ascii 或 rich)",
        choices=["ascii", "rich"],
        default="ascii",
    )
    parser.add_argument(
        "--color-theme",
        help=f"颜色主题: subtle(蓝灰) vibrant(红绿)，默认 subtle",
        choices=list(THEMES.keys()),
        default="subtle",
    )
    parser.add_argument(
        "--export",
        help="导出K线数据到文件 (csv/json)",
        choices=["csv", "json"],
    )
    parser.add_argument(
        "--export-file",
        help="导出文件路径",
        type=str,
    )
    parser.add_argument(
        "-w", "--watch",
        help="持续监控模式，每隔N秒刷新 (默认禁用)",
        type=int,
    )
    return parser


def export_kline_data(kline_data, fmt: str, filepath: str | None) -> None:
    if not kline_data:
        console.print("[yellow]没有K线数据可导出[/yellow]")
        return

    if filepath is None:
        filepath = f"kline_data.{fmt}"

    records = [
        {
            "date": k.date,
            "open": k.open,
            "close": k.close,
            "high": k.high,
            "low": k.low,
            "volume": k.volume,
        }
        for k in kline_data
    ]

    if fmt == "json":
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    elif fmt == "csv":
        import csv
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)

    console.print(f"[green]K线数据已导出到: {filepath}[/green]")


async def process_stocks(args: argparse.Namespace, stocks: list[str]) -> None:
    theme = THEMES[args.color_theme]
    stocks_by_type: dict[str, list[str]] = {}
    for code in stocks:
        info = get_market_info(code)
        if info is None:
            console.print(f"[red]不支持的股票代码格式: {code}[/red]")
            continue
        stocks_by_type.setdefault(info["type"], []).append(code)

    all_stocks = await fetch_realtime(stocks)
    if not all_stocks:
        console.print("[red]未能获取到任何股票数据[/red]")
        return

    print_realtime_table(all_stocks, show_head=args.show_head)

    for stock in all_stocks:
        if args.day or args.week:
            for ktype in ("day", "week"):
                if ktype == "day" and not args.day:
                    continue
                if ktype == "week" and not args.week:
                    continue
                try:
                    kline_data = await fetch_kline(stock.code, ktype, args.period)
                except ValueError as e:
                    console.print(f"[yellow]{e}[/yellow]")
                    continue

                if not kline_data:
                    continue

                if args.chart_type == "ascii":
                    chart = plot_ascii_kline(kline_data, height=args.height, theme=theme)
                    ktype_name = "日" if ktype == "day" else "周"
                    console.print(
                        f"\n[yellow]{stock.name}({stock.code}) {ktype_name}K线图 ({len(kline_data)}个周期):[/yellow]"
                    )
                    console.print(
                        f"[yellow]价格走势 ({theme.close_label}:收盘价 {theme.high_label}:最高价 {theme.low_label}:最低价)[/yellow]"
                    )
                    console.print(chart)

                    dates = [k.date for k in kline_data]
                    console.print(f"\n[cyan]时间范围:[/cyan]")
                    console.print(f"{dates[0]} 至 {dates[-1]}")

                    closes = [k.close for k in kline_data]
                    highs = [k.high for k in kline_data]
                    lows = [k.low for k in kline_data]
                    console.print(f"\n[cyan]价格统计:[/cyan]")
                    console.print(f"[green]最高: {max(highs):.2f}[/green]")
                    console.print(f"[red]最低: {min(lows):.2f}[/red]")
                    console.print(f"[yellow]平均: {sum(closes)/len(closes):.2f}[/yellow]")
                    price_change = (
                        (closes[-1] - closes[0]) / closes[0] * 100
                    ) if closes[0] else 0.0
                    console.print(f"[cyan]区间涨跌: {price_change:.2f}%[/cyan]")

                    console.print("\n[cyan]成交量:[/cyan]")
                    console.print(render_ascii_volume(kline_data, width=40, theme=theme))

                else:
                    panel = build_kline_panel(kline_data, stock.name, stock.code, ktype, args.height, theme=theme)
                    console.print(panel)
                    vol_panel = build_volume_panel(kline_data, width=40, theme=theme)
                    console.print(vol_panel)
                    stat_table = build_stat_table(kline_data)
                    console.print(stat_table)

                if args.ai:
                    patterns = analyze_kline_pattern(kline_data)
                    if patterns:
                        console.print("\n[magenta]AI分析:[/magenta]")
                        console.print("[yellow]发现K线形态:[/yellow]")
                        for p in patterns:
                            console.print(f"- {p.type} ({p.position})")
                            console.print(f"  {p.meaning}")

                    trend = analyze_trend(kline_data)
                    if trend:
                        console.print(f"\n[yellow]趋势分析:[/yellow]")
                        console.print(f"- 当前趋势: {trend.trend} ({trend.strength})")
                        console.print(f"- 分析建议: {trend.analysis}")

                if args.export:
                    export_kline_data(kline_data, args.export, args.export_file)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "analyze":
        parser = build_analyze_parser()
        args = parser.parse_args(sys.argv[2:])
        from .ai_report import run_analyze
        asyncio.run(run_analyze(args))
        return

    parser = build_parser()
    args = parser.parse_args()

    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        stocks = config_data.get("stocks", [])
    elif args.stock:
        stocks = args.stock
    else:
        # Try reading from stdin
        if not sys.stdin.isatty():
            input_data = sys.stdin.read().strip()
            if input_data:
                stocks = [s.strip() for s in input_data.replace("\n", ",").split(",") if s.strip()]
            else:
                parser.print_help()
                return
        else:
            parser.print_help()
            return

    async def run():
        if args.watch:
            import time
            while True:
                console.clear()
                await process_stocks(args, stocks)
                console.print(f"\n[dim]下次刷新在 {args.watch} 秒后... (Ctrl+C退出)[/dim]")
                time.sleep(args.watch)
        else:
            await process_stocks(args, stocks)

    asyncio.run(run())
