from rich.console import Console
from rich.table import Table
from rich import box

from .models import StockRealtime

console = Console()


def print_realtime_table(stocks: list[StockRealtime], show_head: bool = True) -> None:
    table = Table(
        "名字",
        "代码",
        "当前股价",
        "今日涨跌幅",
        "昨日收盘价",
        box=box.SIMPLE,
        show_header=show_head,
    )

    for s in stocks:
        price_str = f"{s.currency}{s.price:.2f}"
        prev_close_str = f"{s.currency}{s.prev_close:.2f}"
        change_str = f"{s.change_pct:.2f}%"

        if s.change_pct > 0:
            change_str = f"[green]{change_str}[/green]"
            price_str = f"[green]{price_str}[/green]"
        elif s.change_pct < 0:
            change_str = f"[red]{change_str}[/red]"
            price_str = f"[red]{price_str}[/red]"

        name = f"{s.name}({s.market})"

        table.add_row(name, s.code, price_str, change_str, prev_close_str)

    console.print("\n实时行情:")
    console.print(table)
