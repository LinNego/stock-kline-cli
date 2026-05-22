import argparse
import asyncio
import os
import re
from datetime import date
from urllib.parse import urlparse

from openai import AsyncOpenAI, APIError

from .ai_prompt import DEFAULT_PROMPT
from .fetcher import get_market_info, fetch_realtime, fetch_kline
from .search import search_stock, SEARCH_BACKENDS, PRIMARY_DOMAINS, SECONDARY_DOMAINS, _extract_urls

SOURCE_PRIORITY_MAP = {}
for d in PRIMARY_DOMAINS:
    SOURCE_PRIORITY_MAP[d] = "⚡一级(官方)"
for d in SECONDARY_DOMAINS:
    SOURCE_PRIORITY_MAP[d] = "📰二级(媒体)"


def _classify_source(url: str) -> str:
    if not url:
        return ""
    try:
        domain = urlparse(url).netloc.lower()
        for known_domain, priority in SOURCE_PRIORITY_MAP.items():
            if known_domain in domain:
                return priority
        return "其他来源"
    except Exception:
        return ""


def _annotate_search_content(content: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {"⚡一级(官方)": 0, "📰二级(媒体)": 0, "其他来源": 0}
    url_pattern = re.compile(r'\(https?://[^)]+\)')
    
    def _replacer(match):
        url = match.group(0)[1:-1]
        priority = _classify_source(url)
        if priority in counts:
            counts[priority] += 1
        return f"{match.group(0)} {priority}"

    annotated = url_pattern.sub(_replacer, content)
    return annotated, counts


def _get_api_key(args: argparse.Namespace) -> str:
    key = args.ai_api_key or os.environ.get("STOCK_KLINE_API_KEY")
    if not key:
        raise ValueError(
            "未设置 API Key。请通过 --ai-api-key 参数或设置 STOCK_KLINE_API_KEY 环境变量"
        )
    return key


def _build_user_message(
    name: str,
    code: str,
    market_name: str,
    price: float,
    change_pct: float,
    search_results,
) -> str:
    lines = [f"请分析 {name}({code})，以下是基础数据和我为你搜索到的参考资料："]

    lines.append(f"\n## 基础数据")
    lines.append(f"- 股票名称: {name}")
    lines.append(f"- 股票代码: {code}")
    lines.append(f"- 市场: {market_name}")
    lines.append(f"- 最新价: {price}")
    lines.append(f"- 涨跌幅: {change_pct:.2f}%")

    lines.append(f"\n## 搜索结果（已为你完成联网搜索，括号内标注了来源优先级，请直接使用以下内容进行分析）")
    total_counts: dict[str, int] = {"⚡一级(官方)": 0, "📰二级(媒体)": 0, "其他来源": 0}
    for sr in search_results:
        if sr.content:
            annotated, counts = _annotate_search_content(sr.content[:4000])
            for k, v in counts.items():
                total_counts[k] += v
            lines.append(f"\n### 搜索: {sr.query}")
            lines.append(annotated)
        else:
            lines.append(f"\n### 搜索: {sr.query} (无结果)")

    total = sum(total_counts.values())
    if total > 0:
        summary_parts = [f"  - {k}: {v}条" for k, v in total_counts.items() if v > 0]
        lines.append(f"\n### 搜索结果来源分布")
        lines.append("\n".join(summary_parts))
        lines.append("")

    lines.append(
        f"\n请严格按照系统提示词中的【输出结构】生成完整的跟踪分析报告。"
        f"注意：联网搜索已由系统自动完成，搜索结果已在上面提供，请直接使用这些结果进行分析，"
        f"无需自行搜索。"
        f"特别注意：必须完成利空风险排查、概念题材想象延伸和未来催化剂分析。"
        f"分析日期: {date.today().isoformat()}"
    )
    return "\n".join(lines)


async def run_analyze(args: argparse.Namespace) -> None:
    code = args.stock_code
    market_info = get_market_info(code)
    if not market_info:
        print(f"错误: 不支持的股票代码格式: {code}")
        return

    api_key = _get_api_key(args)

    print(f"\n正在获取 {code} 实时数据...")
    stocks = await fetch_realtime([code])
    if not stocks:
        print("错误: 未能获取股票数据")
        return
    stock = stocks[0]

    print(f"正在获取 {code} K线数据...")
    try:
        kline_data = await fetch_kline(code, "day", 40)
    except ValueError as e:
        print(f"K线数据获取失败: {e}")
        kline_data = []

    industry_map = {
        "sh": "银行 证券 保险 金融",
        "sz": "银行 证券 保险 金融",
        "hk": "港股",
        "us": "美股",
    }
    industry = industry_map.get(code[:2].lower(), "")

    if args.no_search:
        print("已跳过搜索（--no-search）")
        search_results = []
    else:
        search_sources = getattr(args, "search_sources", "balanced")
        sources_label = {"balanced": "优先官方→自动扩大", "primary": "仅官方来源", "all": "官方+权威媒体"}
        print(f"正在搜索相关信息 (后端: {SEARCH_BACKENDS.get(args.search_backend, args.search_backend)}, 模式: {args.search_mode}, 来源: {sources_label.get(search_sources, search_sources)}, 超时 {args.search_timeout}s)...")
        if args.proxy:
            print(f"代理: {args.proxy}")
        import time as time_mod
        t0 = time_mod.time()
        search_results = await search_stock(
            stock.name, code, industry=industry,
            backend=args.search_backend, timeout=args.search_timeout,
            proxy=args.proxy, mode=args.search_mode,
            search_sources=search_sources,
        )
        elapsed = time_mod.time() - t0
        hit_count = sum(1 for sr in search_results if sr.content)
        print(f"搜索完成 ({hit_count}/{len(search_results)} 个结果, 耗时 {elapsed:.1f}s)")
        if not any(sr.content for sr in search_results):
            print("搜索无结果（网络可能不通），将仅基于基础数据进行分析。")

    prompt_text = DEFAULT_PROMPT
    if args.prompt:
        with open(args.prompt, "r", encoding="utf-8") as f:
            prompt_text = f.read()

    user_msg = _build_user_message(
        name=stock.name,
        code=code,
        market_name=market_info["name"],
        price=stock.price,
        change_pct=stock.change_pct,
        search_results=search_results,
    )

    print(f"\n正在调用 AI 模型 ({args.ai_model})...\n")
    print("=" * 60)
    print()

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=args.ai_base_url,
    )

    try:
        response = await client.chat.completions.create(
            model=args.ai_model,
            messages=[
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": user_msg},
            ],
            stream=True,
            temperature=0.7,
            max_tokens=8192,
        )

        collected = []
        async for chunk in response:
            content = chunk.choices[0].delta.content or ""
            print(content, end="", flush=True)
            collected.append(content)
        print()

    except APIError as e:
        print(f"\nAI API 调用失败: {e}")
        print(f"请检查 --ai-base-url ({args.ai_base_url}) 和 --ai-model ({args.ai_model}) 是否正确")
        return
    except Exception as e:
        print(f"\n未知错误: {e}")
        return

    print()
    print("=" * 60)
    print(f"分析日期: {date.today().isoformat()}")
    print(f"数据来源: 腾讯股票API + {SEARCH_BACKENDS.get(args.search_backend, args.search_backend)}")
    all_urls = []
    for sr in search_results:
        all_urls.extend(_extract_urls(sr.content))
    if all_urls:
        print(f"搜索页面来源 ({len(all_urls)} 个):")
        for url in all_urls[:10]:
            print(f"  {url}")
        if len(all_urls) > 10:
            print(f"  ... 及其他 {len(all_urls) - 10} 个页面")
    print("说明: 本报告由 AI 自动生成，仅供参考，不构成投资建议。")
    print()
