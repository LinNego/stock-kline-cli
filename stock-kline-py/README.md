# stock-kline-py

在终端上打印股票实时数据和K线图的命令行工具（Python版）。支持 A股、港股、美股。

基于 [stock-kline-cli](https://github.com/OnePieceJoker/stock-kline-cli) 的 Python 重构版，新增更多功能。

## 安装

```bash
# 方式一：从本地源码安装（开发/修改代码时推荐）
cd stock-kline-py
pip install -e .

# 方式二：基础安装（实时行情 + K线图）
pip install httpx rich

# 如需 AI 深度分析功能
pip install openai

# 如果遇到外部包管理限制，加上 --break-system-packages
pip install --break-system-packages -e .
pip install --break-system-packages openai
```

`pip install -e .` 会创建 `stock-kline` 命令（指向 `stock_kline.cli:main`），
且安装的是可编辑模式，修改源码后即时生效，无需重新安装。

## 使用

### 实时行情

```bash
# 查看单个股票
stock-kline -s sh600000

# 查看多个股票
stock-kline -s sh600000,sz000001

# 美股/港股
stock-kline -s usAAPL
stock-kline -s hk00700
```

### K线图

```bash
# 显示日K线图
stock-kline -s sh600000 --day

# 显示周K线图
stock-kline -s sh600000 --week

# 同时显示日K和周K
stock-kline -s sh600000 --day --week

# 设置周期数（默认40）
stock-kline -s sh600000 --day -p 60

# 设置图表高度（默认15）
stock-kline -s sh600000 --day --height 20
```

### 图表样式

```bash
# ASCII 纯字符图表（默认）
stock-kline -s sh600000 --day --chart-type ascii

# Rich 彩色图表
stock-kline -s sh600000 --day --chart-type rich

# 颜色主题：subtle(蓝灰) / vibrant(红绿)
stock-kline -s sh600000 --day --color-theme vibrant
stock-kline -s sh600000 --day --color-theme subtle
```

### AI 深度分析（LLM + 联网搜索）

```bash
# 1. 设置 API Key
export STOCK_KLINE_API_KEY="sk-xxx"
export TAVILY_API_KEY="tvly-xxx"       # Tavily 搜索（推荐，免费 1000次/月）

# 2. 分析个股（默认 auto 模式）
stock-kline analyze sh600000

# 3. 使用自定义 prompt 文件
stock-kline analyze sh600000 --prompt ./prompt

# 4. 指定搜索后端
stock-kline analyze sh600000 --search-backend auto    # 自动（默认）
stock-kline analyze sh600000 --search-backend tavily  # Tavily（需 TAVILY_API_KEY）

# 5. 搜索模式
stock-kline analyze sh600000 --search-mode parallel  # 并行5次搜索，覆盖最全（费credit，默认）
stock-kline analyze sh600000 --search-mode single    # 合并1次搜索，省credit

# 6. 使用代理（WSL 访问宿主机代理）
stock-kline analyze sh600000 --proxy http://172.24.160.1:7897

# 7. 跳过搜索，仅用基础数据
stock-kline analyze sh600000 --no-search

# 8. 指定 LLM 模型（兼容任意 OpenAI API）
stock-kline analyze sh600000 \
  --ai-model deepseek-v4-flash \
  --ai-base-url https://opencode.ai/zen/go/v1

# 9. 全部参数示例
stock-kline analyze sh600000 \
  --prompt ./my_prompt.txt \
  --search-backend tavily \
  --search-mode single \
  --proxy http://172.24.160.1:7897 \
  --ai-model deepseek-v4-flash \
  --ai-base-url https://opencode.ai/zen/go/v1
```

AI 分析调用 LLM 后流式输出完整的跟踪分析报告，包含：
- 核心驱动逻辑（逻辑持续性评分）
- 财务基本面与机构预期
- 历史利空风险排查
- 技术面与资金面
- 概念题材与未来催化剂

AI 分析是独立子命令，不会与 `--watch` 模式冲突。

### 数据导出

```bash
stock-kline -s sh600000 --day --export json
stock-kline -s sh600000 --day --export csv --export-file ./sh600000_kline.csv
```

### 本地规则分析（无需 API）

```bash
stock-kline -s sh600000 --day --ai
```

内置锤子线/启明星形态识别 + MA5/MA10 趋势分析。

### 配置文件

```bash
# config.json
# { "stocks": ["sh600000", "sz000001"] }

stock-kline -c config.json --day
```

## 数据来源

- 实时数据：腾讯股票 API（qt.gtimg.cn）
- K线数据：腾讯股票 API（web.ifzq.gtimg.cn）
- AI 搜索：Tavily

## 依赖

| 组件 | 用途 |
|------|------|
| httpx | HTTP 请求 |
| rich | 彩色图表 + 表格 |
| openai | LLM API 调用（可选） |

## License

ISC
