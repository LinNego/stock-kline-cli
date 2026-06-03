import asyncio
import concurrent.futures
import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

SEARCH_BACKENDS = {
    "tavily": "Tavily",
    "auto": "自动(优先使用Tavily，可扩展其他后端)",
}

# 搜索来源域名分级
PRIMARY_DOMAINS = [
    "cninfo.com.cn",
    "sse.com.cn",
    "szse.cn",
    "bse.cn",
    "nfra.gov.cn",
]

SECONDARY_DOMAINS = [
    "eastmoney.com",
    "stcn.com",
    "finance.sina.com.cn",
    "cls.cn",
    "wallstreetcn.com",
    "stockstar.com",
    "gelonghui.com",
    "10jqka.com.cn",
    "cczs.net.cn",
]

ALL_SEARCH_DOMAINS = PRIMARY_DOMAINS + SECONDARY_DOMAINS

NOISE_KEYWORDS = [
    "API认证错误", "认证失败", "403 Forbidden", "404 Not Found",
    "500 Internal", "502 Bad Gateway", "503 Service",
    "access denied", "captcha", "verify you are human",
    "please enable javascript", "您的请求",
]


def _detect_proxy() -> str | None:
    for var in ("ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "all_proxy", "https_proxy", "http_proxy"):
        val = os.environ.get(var)
        if val:
            return val
    return None


PROXY = _detect_proxy()


def _make_httpx_client(timeout: float, proxy: str | None = None) -> httpx.AsyncClient:
    kwargs = {"timeout": timeout}
    if proxy or PROXY:
        kwargs["proxy"] = proxy or PROXY
    return httpx.AsyncClient(**kwargs)


def _clean_content(text: str) -> str:
    if not text:
        return ""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(kw.lower() in stripped.lower() for kw in NOISE_KEYWORDS):
            continue
        cleaned.append(stripped)
    return "\n".join(cleaned[:20])


def _extract_urls(text: str) -> list[str]:
    urls = re.findall(r'\(https?://[^)]+\)', text)
    seen = set()
    result = []
    for u in urls:
        url = u[1:-1]
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


async def _fetch_single_page(url: str, timeout: float = 5.0, proxy: str | None = None) -> str:
    try:
        async with _make_httpx_client(timeout, proxy=proxy) as client:
            resp = await client.get(url, follow_redirects=True)
        text = resp.text[:6000]
        return _clean_content(text)[:4000]
    except Exception:
        return ""


async def _enrich_with_page_content(content: str, timeout: float = 5.0, proxy: str | None = None) -> str:
    urls = _extract_urls(content)
    if not urls:
        return content

    tasks = [_fetch_single_page(url, timeout=timeout, proxy=proxy) for url in urls[:10]]
    pages = await asyncio.gather(*tasks)

    parts = [content]
    for url, page_text in zip(urls[:10], pages):
        if page_text:
            parts.append(f"\n--- 页面原文 ({url}) ---\n{page_text}")
    return "\n".join(parts)


@dataclass
class SearchResult:
    query: str
    content: str
    source: str


async def search_jina(query: str, timeout: float = 5.0, proxy: str | None = None) -> str:
    url = f"https://s.jina.ai/{query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; StockKline/1.0)",
        "Accept": "text/plain",
    }
    try:
        async with _make_httpx_client(timeout, proxy=proxy) as client:
            resp = await client.get(url, headers=headers, follow_redirects=True)
        return _clean_content(resp.text[:3000])
    except Exception:
        return ""


async def search_brave(query: str, timeout: float = 5.0, proxy: str | None = None) -> str:
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY")
    if not api_key:
        return ""

    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": 5}
    try:
        async with _make_httpx_client(timeout, proxy=proxy) as client:
            resp = await client.get(url, headers=headers, params=params)

        if resp.status_code != 200:
            return ""

        data = resp.json()
        results = data.get("web", {}).get("results", [])
    except Exception:
        return ""

    lines = []
    for r in results:
        title = r.get("title", "")
        desc = r.get("description", "")
        url_link = r.get("url", "")
        lines.append(f"- {title}: {desc} ({url_link})")
    return "\n".join(lines) if lines else ""


async def search_tavily(query: str, timeout: float = 5.0, proxy: str | None = None,
                        include_domains: list[str] | None = None) -> str:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        import sys
        print("[search_tavily] TAVILY_API_KEY 未设置", file=sys.stderr)
        return ""

    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": 20,
    }
    if include_domains:
        payload["include_domains"] = include_domains
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            import sys
            print(f"[search_tavily] HTTP {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
            return ""
        data = resp.json()
    except Exception:
        return ""

    results = data.get("results", [])
    lines = []
    for r in results:
        title = r.get("title", "")
        content = r.get("content", "")
        url_link = r.get("url", "")
        lines.append(f"- {title}: {content} ({url_link})")
    return "\n".join(lines) if lines else ""


async def search_duckduckgo(query: str, timeout: float = 5.0, proxy: str | None = None) -> str:
    ddgs = _try_import_ddgs()
    if ddgs is None:
        return ""

    proxy_url = proxy or PROXY

    def _run():
        try:
            kwargs = {}
            if proxy_url:
                kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}
            with ddgs.DDGS(timeout=timeout, **kwargs) as ddgs_client:
                results = list(ddgs_client.text(query, max_results=5))
                lines = []
                for r in results:
                    title = r.get("title", "")
                    body = r.get("body", "")
                    lines.append(f"- {title}: {body}")
                return "\n".join(lines) if lines else ""
        except Exception:
            return ""

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = loop.run_in_executor(pool, _run)
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except (asyncio.TimeoutError, Exception):
            pool.shutdown(wait=False, cancel_futures=True)
            return ""


def _try_import_ddgs():
    try:
        from ddgs import DDGS as _ddgs
        return type("_ddgs_mod", (), {"DDGS": _ddgs})()
    except ImportError:
        pass
    try:
        from duckduckgo_search import DDGS as _ddgs
        return type("_ddgs_mod", (), {"DDGS": _ddgs})()
    except ImportError:
        pass
    return None


async def _search_tavily_with_sources(
    query: str,
    timeout: float = 5.0,
    proxy: str | None = None,
    search_sources: str = "balanced",
) -> str:
    if search_sources == "primary":
        content = await search_tavily(query, timeout=timeout, proxy=proxy, include_domains=PRIMARY_DOMAINS)
        return await _enrich_with_page_content(content, timeout=timeout, proxy=proxy)

    if search_sources == "all":
        content = await search_tavily(query, timeout=timeout, proxy=proxy, include_domains=ALL_SEARCH_DOMAINS)
        return await _enrich_with_page_content(content, timeout=timeout, proxy=proxy)

    if search_sources == "balanced":
        content = await search_tavily(query, timeout=timeout, proxy=proxy, include_domains=PRIMARY_DOMAINS)
        if _clean_content(content):
            return await _enrich_with_page_content(content, timeout=timeout, proxy=proxy)
        content = await search_tavily(query, timeout=timeout, proxy=proxy, include_domains=ALL_SEARCH_DOMAINS)
        return await _enrich_with_page_content(content, timeout=timeout, proxy=proxy)

    content = await search_tavily(query, timeout=timeout, proxy=proxy)
    return await _enrich_with_page_content(content, timeout=timeout, proxy=proxy)


async def search(query: str, backend: str = "jina", timeout: float = 5.0,
                 proxy: str | None = None, search_sources: str = "balanced") -> SearchResult:
    if backend == "auto":
        return await _search_auto(query, timeout=timeout, proxy=proxy, search_sources=search_sources)

    try:
        if backend == "tavily":
            content = await _search_tavily_with_sources(query, timeout=timeout, proxy=proxy, search_sources=search_sources)
        else:
            content = ""
    except Exception:
        content = ""

    return SearchResult(query=query, content=content, source=backend)


async def _search_auto(query: str, timeout: float = 5.0, proxy: str | None = None,
                       search_sources: str = "balanced") -> SearchResult:
    async def try_tavily():
        try:
            return "tavily", await _search_tavily_with_sources(query, timeout=timeout, proxy=proxy, search_sources=search_sources)
        except Exception:
            return "tavily", ""

    priority = [asyncio.create_task(try_tavily())]

    for coro in asyncio.as_completed(priority):
        name, content = await coro
        if _clean_content(content):
            for c in priority:
                c.cancel()
            return SearchResult(query=query, content=content, source=name)

    return SearchResult(query=query, content="", source="auto")


async def search_stock(
    name: str,
    code: str,
    industry: str = "",
    backend: str = "jina",
    timeout: float = 5.0,
    proxy: str | None = None,
    mode: str = "parallel",
    search_sources: str = "balanced",
) -> list[SearchResult]:
    if mode == "single":
        combined = f"{name} {code} 最新公告 财报 业绩 营收 净利润 立案 处罚 监管 研报 评级"
        if industry:
            combined += f" {industry} 政策 2026"
        result = await search(combined, backend=backend, timeout=timeout, proxy=proxy, search_sources=search_sources)
        return [result]

    queries = [
        f"{name} {code} 最新公告",
        f"{name} {code} 财报 业绩 营收 净利润",
        f"{name} {code} 立案 处罚 违规 监管",
        f"{name} {code} 研报 评级",
    ]
    if industry:
        queries.append(f"{industry} 政策 2026")

    tasks = [search(q, backend=backend, timeout=timeout, proxy=proxy, search_sources=search_sources) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if isinstance(r, SearchResult)]
