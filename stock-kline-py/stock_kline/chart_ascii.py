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

    closes = [k.close for k in kline_data]
    highs = [k.high for k in kline_data]
    lows = [k.low for k in kline_data]

    return plot_lines([closes, highs, lows], height=height, theme=theme)


def render_volume(kline_data: list[KLine], width: int = 60, theme: ColorTheme | None = None) -> str:
    if theme is None:
        theme = THEMES["subtle"]

    if not kline_data:
        return ""

    volumes = [k.volume for k in kline_data]
    vol_max = max(volumes)
    if vol_max == 0:
        return ""

    block_chars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
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
    max_v_str = f"{vol_max / 100000000:.2f}亿"
    avg_v_str = f"{vol_avg / 100000000:.2f}亿"
    line += f"  量: 最高{max_v_str} 均{avg_v_str}"
    return line
