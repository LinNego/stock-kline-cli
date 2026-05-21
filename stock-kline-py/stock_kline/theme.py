from dataclasses import dataclass


@dataclass
class ColorTheme:
    name: str
    up_ansi: str
    down_ansi: str
    close_ansi: str
    high_ansi: str
    low_ansi: str
    up_rich: str
    down_rich: str
    close_label: str
    high_label: str
    low_label: str


THEMES: dict[str, ColorTheme] = {
    "subtle": ColorTheme(
        name="subtle",
        up_ansi="34",
        down_ansi="90",
        close_ansi="34",
        high_ansi="36",
        low_ansi="90",
        up_rich="blue",
        down_rich="grey",
        close_label="蓝色",
        high_label="青色",
        low_label="灰色",
    ),
    "vibrant": ColorTheme(
        name="vibrant",
        up_ansi="32",
        down_ansi="31",
        close_ansi="34",
        high_ansi="32",
        low_ansi="31",
        up_rich="green",
        down_rich="red",
        close_label="蓝色",
        high_label="绿色",
        low_label="红色",
    ),
}
