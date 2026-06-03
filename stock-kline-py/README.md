# stock-kline-py

在终端上打印股票和期货实时数据、K线图、信号回测的命令行工具（Python版）。

## 安装

```bash
cd stock-kline-py
pip install -e .
pip install --break-system-packages -e .
```

如需 AI 分析：`pip install openai`

## 实时行情

```bash
# A股
stock-kline -s sh600000

# 期货
stock-kline -s nf_V            # PVC
stock-kline -s nf_TA           # PTA
stock-kline -s nf_RB           # 螺纹钢
stock-kline -s nf_CU           # 沪铜

# 多个
stock-kline -s sh600000,nf_V,nf_RB

# 数据来源：AKShare(期货) / 腾讯API(股票)
```

## K线图（日/周）

```bash
stock-kline -s nf_V --day           # 日K
stock-kline -s nf_V --week          # 周K
stock-kline -s nf_V --day -p 60     # 60个周期
stock-kline -s sh600000 --day       # 股票日K
```

## 5分钟K线（实时更新）

每5分钟边界自动从AKShare拉取已完成K线，无需轮询：

```bash
stock-kline chart nf_V -i 5                      # 完整模式（蓝色K线）
stock-kline chart nf_V -i 5 --stealth            # 摸鱼模式（灰白K线，只显示图）
stock-kline chart nf_V -i 5 --stealth --height 3 # 3行高的迷你K线
stock-kline chart nf_V -i 5 --signal             # 信号提示
stock-kline chart nf_V -i 5 --disguise            # 伪装终端标题
stock-kline chart nf_V -i 5 --stealth --disguise --height 3  # 终极摸鱼
stock-kline chart nf_V -i 5 --bars 60            # 显示60根
```

## 摸鱼/伪装

```bash
# 纯数字（最隐蔽）
stock-kline -w 3 -s nf_V --stealth

# 灰白K线 + 区间最高/最低/当前收盘
stock-kline chart nf_V -i 5 --stealth --height 3

# 加上伪装标题
stock-kline chart nf_V -i 5 --stealth --disguise --height 3
```

摸鱼 `--stealth` 模式下，左侧显示三个价格：
- **H** — 区间最高
- **数字** — 当前收盘（颜色跟随涨跌）
- **L** — 区间最低

## 信号策略

内置策略，`--signal` 时生效：

| 策略 | 参数 | 说明 |
|------|------|------|
| `breakout` | `--strategy breakout` | 平台盘整后放量突破（默认） |
| `ma_cross` | `--strategy ma_cross` | MA5/MA10金叉死叉 |
| `vol_spike` | `--strategy vol_spike` | 单根放量 |

```bash
stock-kline chart nf_TA -i 5 --signal --strategy ma_cross
```

## 回测模式

用历史K线逐bar推进检测信号，信号触发时暂停展示K线+量图：

```bash
# 单品种
stock-kline chart nf_TA -i 5 --bars 30 --replay --signal

# 多品种
stock-kline chart nf_TA,nf_V,nf_RB -i 5 --bars 20 --replay --signal

# 指定策略
stock-kline chart nf_TA -i 5 --replay --signal --strategy ma_cross

# 回放速度（秒/bar）
stock-kline chart nf_TA -i 5 --replay 0.1 --signal

# 自定义策略文件
stock-kline chart nf_TA -i 5 --replay --signal --strategy-file ./my_strat.py
```

自定义策略示例：

```python
from stock_kline.futures.strategies import Strategy

class MyStrategy(Strategy):
    name = "my_strat"
    description = "..."
    def check(self, bars):
        # bars: list[KLine]
        # 返回 {"strategy":self.name, "direction":"up"/"down", ...} 或 None
        ...
```

## 监控模式

```bash
stock-kline -w 3 -s nf_V            # 每3秒刷新
stock-kline -w 30 -s sh600000,nf_V  # 每30秒刷新
stock-kline -w 3 -s nf_V --stealth  # 摸鱼模式
```

## AI深度分析

```bash
export STOCK_KLINE_API_KEY="sk-xxx"
stock-kline analyze sh600000
stock-kline analyze sh600000 --no-search
stock-kline analyze sh600000 --proxy http://127.0.0.1:7897
```

## 数据导出

```bash
stock-kline -s nf_V --day --export json
stock-kline -s nf_V --day --export csv --export-file ./kline.csv
```

## 项目结构

```
stock_kline/
  ├── cli.py               # CLI入口
  ├── common/               # 公共组件
  │   ├── models.py         # 数据模型
  │   ├── chart_ascii.py    # ASCII K线绘制
  │   ├── chart_rich.py     # Rich彩色图表
  │   ├── display.py        # 表格显示
  │   └── analysis.py       # 形态识别
  ├── stock/                # 股票
  │   └── fetcher.py        # 腾讯API
  ├── futures/              # 期货
  │   ├── fetcher.py        # AKShare数据源
  │   ├── chart.py          # 实时K线+回测
  │   └── strategies.py     # 信号策略框架
  └── ai/                   # AI分析
```

## License

ISC
