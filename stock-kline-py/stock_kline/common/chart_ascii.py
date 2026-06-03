from .models import KLine
from .theme import ColorTheme, THEMES


def _scale(values: list[float], height: int) -> tuple[list[int], float, float]:
    if not values:
        return [], 0, 0
    vmin = min(values)
    vmax = max(values)
    span = vmax - vmin
    if span == 0:
        return [height // 2] * len(values), vmin, vmax
    scaled = [int((v - vmin) / span * (height - 1)) for v in values]
    return scaled, vmin, vmax


def plot_lines(
    series_list: list[list[float]],
    height: int = 15,
    width: int | None = None,
    theme: ColorTheme | None = None,
) -> str:
    if theme is None:
        theme = THEMES["subtle"]

    ansi_map = {
        "close": f"\033[{theme.close_ansi}m",
        "high": f"\033[{theme.high_ansi}m",
        "low": f"\033[{theme.low_ansi}m",
        "reset": "\033[0m",
    }
    ansi_keys = ["close", "high", "low"]

    if not series_list or not series_list[0]:
        return ""

    n = len(series_list[0])
    if width is None or width > n:
        width = n

    scaled_all = []
    for series in series_list:
        s, _mn, _mx = _scale(series, height)
        scaled_all.append(s)

    lines = []
    for row in range(height - 1, -1, -1):
        line_chars = []
        for col in range(width):
            for si, scaled in enumerate(scaled_all):
                if col < len(scaled) and scaled[col] == row:
                    line_chars.append(f"{ansi_map[ansi_keys[si]]}●{ansi_map['reset']}")
                    break
                if col < len(scaled) and scaled[col] > row:
                    line_chars.append(f"{ansi_map[ansi_keys[0]]}│{ansi_map['reset']}")
                    break
            else:
                line_chars.append(" ")
        lines.append("".join(line_chars))

    return "\n".join(lines)


def plot_kline(kline_data: list[KLine], height: int = 15, theme: ColorTheme | None = None) -> str:
    if not kline_data:
        return ""

    if theme is None:
        theme = THEMES["subtle"]

    all_prices = []
    for k in kline_data:
        all_prices.extend([k.high, k.low, k.open, k.close])
    vmin = min(all_prices)
    vmax = max(all_prices)
    span = vmax - vmin

    def _scale_price(p: float) -> int:
        if span == 0:
            return 0
        return int((p - vmin) / span * (height - 1))

    up_ansi = f"\033[{theme.up_ansi}m"
    down_ansi = f"\033[{theme.down_ansi}m"
    wick_ansi = f"\033[{theme.close_ansi}m"
    reset = "\033[0m"

    lines = []
    for row in range(height - 1, -1, -1):
        chars = []
        for k in kline_data:
            h = _scale_price(k.high)
            l_ = _scale_price(k.low)
            o = _scale_price(k.open)
            c = _scale_price(k.close)

            body_top = max(o, c)
            body_bot = min(o, c)
            is_up = k.close >= k.open
            body_ansi = up_ansi if is_up else down_ansi

            if row > h or row < l_:
                chars.append(" ")
            elif row == h and row == l_:
                chars.append(f"{body_ansi}━{reset}")
            elif body_bot <= row <= body_top:
                chars.append(f"{body_ansi}┃{reset}")
            else:
                chars.append(f"{wick_ansi}│{reset}")

        lines.append("".join(chars))

    return "\n".join(lines)


def render_volume(kline_data: list[KLine], width: int = 60, theme: ColorTheme | None = None, compact: bool = False) -> str:
    if theme is None:
        theme = THEMES["subtle"]

    if not kline_data:
        return ""

    volumes = [k.volume for k in kline_data]
    vol_max = max(volumes)
    if vol_max == 0:
        return ""

    block_chars = [chr(0x2581 + i) for i in range(8)]
    n = len(volumes)
    step = max(1, n // width)
    line = ""
    for i in range(0, n, step):
        v = volumes[i]
        ratio = v / vol_max
        idx = min(len(block_chars) - 1, int(ratio * len(block_chars)))
        is_up = kline_data[i].close >= kline_data[i].open
        code = theme.up_ansi if is_up else theme.down_ansi
        line += f"\033[{code}m{block_chars[idx]}\033[0m"

    vol_avg = sum(volumes) / n
    if not compact:
        max_v_str = f"{vol_max / 100000000:.2f}亿"
        avg_v_str = f"{vol_avg / 100000000:.2f}亿"
        line += f"  量: 最高{max_v_str} 均{avg_v_str}"
    return line
