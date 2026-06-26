"""
China-friendly multi-provider search module.

Replaces the DDGS-only search layer with a multi-backend approach that works
reliably from within China's GFW. Bing is the primary provider (accessible from
China without VPN), with DDGS as a configurable fallback.

P2-7: 搜索层优化 — 国内可用的多搜索引擎搜索模块
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import quote_plus

import requests

from config import get_logger

# ---- Search result format ----
# Each result dict: {"title": str, "body": str, "href": str}
# This matches the DDGS text() return format for drop-in compatibility.

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_DEFAULT_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
}

# ---- Provider configuration ----
# Load defaults from config.py, fall back to hardcoded values if unavailable.
try:
    from config import SEARCH_CONFIG

    DEFAULT_PROVIDER_ORDER: list[str] = SEARCH_CONFIG.get("provider_order", ["bing", "ddgs_api"])
    SEARCH_TIMEOUT: int = SEARCH_CONFIG.get("timeout", 12)
    RATE_LIMIT_DELAY: float = SEARCH_CONFIG.get("rate_limit_delay", 0.3)
except ImportError:
    DEFAULT_PROVIDER_ORDER = ["bing", "ddgs_api"]
    SEARCH_TIMEOUT = 12
    RATE_LIMIT_DELAY = 0.3

_log = get_logger("search_providers")


# ============================================================================
# Bing Search Provider
# ============================================================================

def _bing_search(
    query: str,
    max_results: int = 8,
    timeout: int = SEARCH_TIMEOUT,
) -> list[dict[str, str]]:
    """
    Search cn.bing.com and extract structured results.

    Bing is accessible from mainland China without VPN and indexes Chinese
    financial/stock content well.

    Args:
        query: Search query string.
        max_results: Max number of results to return (1-20).
        timeout: HTTP request timeout in seconds.

    Returns:
        List of result dicts with 'title', 'body', 'href' keys.
    """
    results: list[dict[str, str]] = []
    try:
        count = min(max_results, 15)
        url = f"https://cn.bing.com/search?q={quote_plus(query)}&count={count}&setmkt=zh-CN"

        resp = requests.get(url, headers=_DEFAULT_HEADERS, timeout=timeout)
        if resp.status_code != 200:
            _log.debug("Bing returned HTTP %d for query: %s", resp.status_code, query[:60])
            return results

        html = resp.text

        # Bing wraps each result in <li class="b_algo">...</li>
        blocks = re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', html, re.DOTALL)
        if not blocks:
            _log.debug("Bing: no b_algo blocks found for query: %s", query[:60])
            return results

        for block in blocks[:max_results]:
            # Extract title + URL from <h2><a href="...">title</a></h2>
            title_match = re.search(
                r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                block, re.DOTALL,
            )
            if not title_match:
                continue

            href = title_match.group(1)
            title = re.sub(r'<[^>]+>', '', title_match.group(2)).strip()
            # Decode common HTML entities
            title = title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')

            # Extract snippet from <p> tag
            snippet = ""
            snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
            if snippet_match:
                snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()
                # Clean up whitespace/entities
                snippet = re.sub(r'&ensp;|&#0183;|·', ' ', snippet)
                snippet = re.sub(r'\s+', ' ', snippet)
                snippet = snippet.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")

            if not title:
                continue

            results.append({
                "title": title,
                "body": snippet,
                "href": href,
            })

    except requests.Timeout:
        _log.debug("Bing search timed out (%.0fs): %s", timeout, query[:60])
    except requests.ConnectionError:
        _log.debug("Bing connection failed: %s", query[:60])
    except Exception:
        _log.debug("Bing search error for query '%s'", query[:60], exc_info=True)

    return results


# ============================================================================
# Bing News Search Provider
# ============================================================================

def _bing_news_search(
    query: str,
    max_results: int = 8,
    timeout: int = SEARCH_TIMEOUT,
) -> list[dict[str, str]]:
    """
    Search cn.bing.com/news for recent news articles.

    Bing News is also accessible from mainland China and gives much more
    timely/relevant results for financial news queries.

    Args:
        query: Search query string.
        max_results: Max number of results to return (1-15).
        timeout: HTTP request timeout in seconds.

    Returns:
        List of result dicts with 'title', 'body', 'href' keys.
    """
    results: list[dict[str, str]] = []
    try:
        count = min(max_results, 15)
        url = f"https://cn.bing.com/news/search?q={quote_plus(query)}&count={count}&setmkt=zh-CN&format=rss"

        resp = requests.get(url, headers=_DEFAULT_HEADERS, timeout=timeout)
        if resp.status_code != 200:
            _log.debug("Bing News returned HTTP %d for query: %s", resp.status_code, query[:60])
            return results

        html = resp.text

        # Bing News uses <div class="news-card"> or similar structures.
        # Each news card contains: title link, snippet, source + time.
        # The structure varies; try multiple extraction patterns.

        # Pattern 1: news-card body with title + snippet
        cards = re.findall(
            r'<div[^>]*class="[^"]*news-card[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
            html, re.DOTALL,
        )
        if not cards:
            # Pattern 2: <a class="title"> inside news result blocks
            cards = re.findall(
                r'<div[^>]*class="[^"]*(?:newsitem|news-card|card-)[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
                html, re.DOTALL,
            )

        if not cards:
            # Fallback: extract all title+link pairs from the page
            # Bing News page has structured links with article titles
            links = re.findall(
                r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
                html, re.DOTALL,
            )
            for href, raw_title in links[:max_results * 2]:
                title = re.sub(r'<[^>]+>', '', raw_title).strip()
                title = title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                # Filter out navigation/UI links (too short or common)
                if len(title) < 10:
                    continue
                if title in ("新闻", "资讯", "首页", "登录", "注册", "更多", "设置"):
                    continue
                # Deduplicate by title
                if any(r["title"] == title for r in results):
                    continue
                results.append({"title": title, "body": "", "href": href})
            return results[:max_results]

        for card in cards[:max_results]:
            # Extract title + URL
            title_match = re.search(
                r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
                card, re.DOTALL,
            )
            if not title_match:
                continue

            href = title_match.group(1)
            title = re.sub(r'<[^>]+>', '', title_match.group(2)).strip()
            title = title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')

            # Extract snippet
            snippet = ""
            snippet_match = re.search(r'<[^>]*class="[^"]*snippet[^"]*"[^>]*>(.*?)</', card, re.DOTALL)
            if not snippet_match:
                snippet_match = re.search(r'<p[^>]*>(.*?)</p>', card, re.DOTALL)
            if snippet_match:
                snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()
                snippet = re.sub(r'\s+', ' ', snippet)
                snippet = snippet.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")

            if not title:
                continue

            results.append({"title": title, "body": snippet, "href": href})

    except requests.Timeout:
        _log.debug("Bing News search timed out (%.0fs): %s", timeout, query[:60])
    except requests.ConnectionError:
        _log.debug("Bing News connection failed: %s", query[:60])
    except Exception:
        _log.debug("Bing News search error for query '%s'", query[:60], exc_info=True)

    return results


# ============================================================================
# DDGS-based providers (fallback)
# ============================================================================

def _ddgs_search(
    query: str,
    max_results: int = 8,
    timeout: int = 10,
    backend: str = "api",
) -> list[dict[str, str]]:
    """
    Search via DDGS library with explicit backend configuration.

    Args:
        query: Search query string.
        max_results: Max number of results to return.
        timeout: Timeout per DDGS connection.
        backend: DDGS backend name (e.g., "api", "yandex").

    Returns:
        List of result dicts with 'title', 'body', 'href' keys.
    """
    results: list[dict[str, str]] = []
    try:
        from ddgs import DDGS

        with DDGS(timeout=timeout) as ddgs:
            for r in ddgs.text(query, max_results=max_results, backend=backend):
                title = (r.get("title") or "").strip()
                body = (r.get("body") or "").strip()
                href = (r.get("href") or "").strip()
                if title or body:
                    results.append({"title": title, "body": body, "href": href})

    except Exception:
        _log.debug("DDGS search failed (backend=%s): %s", backend, query[:60], exc_info=True)

    return results


# ============================================================================
# Multi-provider search
# ============================================================================

# Track last request time per provider for rate limiting
_last_request_time: dict[str, float] = {}


def _rate_limit(provider_name: str) -> None:
    """Ensure minimum delay between requests to the same provider."""
    now = time.time()
    last = _last_request_time.get(provider_name, 0)
    delta = now - last
    if delta < RATE_LIMIT_DELAY:
        time.sleep(RATE_LIMIT_DELAY - delta)
    _last_request_time[provider_name] = time.time()


def search(
    query: str,
    max_results: int = 8,
    provider_order: list[str] | None = None,
    timeout: int = SEARCH_TIMEOUT,
) -> list[dict[str, str]]:
    """
    Search the web using configured providers in priority order.

    Tries each provider until one returns results. Falls through all
    providers gracefully — an empty list means all providers failed.

    Args:
        query: Search query string.
        max_results: Max number of results to return.
        provider_order: List of provider names to try, in order.
            Default: ["bing", "ddgs_api"].
        timeout: HTTP request timeout in seconds.

    Returns:
        List of result dicts, each with 'title', 'body', 'href'.
        Empty list if all providers fail.
    """
    if provider_order is None:
        provider_order = DEFAULT_PROVIDER_ORDER

    for provider_name in provider_order:
        _rate_limit(provider_name)

        if provider_name == "bing":
            results = _bing_search(query, max_results=max_results, timeout=timeout)
        elif provider_name == "bing_news":
            results = _bing_news_search(query, max_results=max_results, timeout=timeout)
        elif provider_name.startswith("ddgs_"):
            backend = provider_name.replace("ddgs_", "")
            results = _ddgs_search(query, max_results=max_results, timeout=min(timeout, 10), backend=backend)
        else:
            _log.warning("Unknown search provider: %s", provider_name)
            continue

        if results:
            _log.debug("Provider '%s' returned %d results for: %s", provider_name, len(results), query[:60])
            return results

    _log.debug("All search providers failed for: %s", query[:60])
    return []


def search_as_text(query: str, max_results: int = 5, **kwargs: Any) -> str:
    """
    Search and return results as concatenated text — drop-in replacement
    for ai_validators._search_web().

    Args:
        query: Search query string.
        max_results: Max number of results.
        **kwargs: Passed through to search().

    Returns:
        Concatenated result text, or empty string if no results.
    """
    results = search(query, max_results=max_results, **kwargs)
    if not results:
        return ""
    lines = []
    for r in results:
        line = f"- {r['title']}: {r['body']}"
        if r.get("href"):
            line += f" | {r['href']}"
        lines.append(line)
    return "\n".join(lines)


def search_news(
    query: str,
    max_results: int = 5,
    **kwargs: Any,
) -> list[dict[str, str]]:
    """
    Search with news-focused query enhancement.

    Appends date qualifiers and financial news keywords to improve
    relevance for A-share theme discovery use cases.

    Args:
        query: Base search query.
        max_results: Max number of results.
        **kwargs: Passed through to search().

    Returns:
        List of result dicts.
    """
    # Enhance query for news relevance if not already news-focused
    news_indicators = ["site:", "涨停", "题材", "概念股", "研报", "近一周", "近期", "202"]
    if not any(indicator in query for indicator in news_indicators):
        enhanced = f"{query} A股 2026"
    else:
        enhanced = query
    return search(enhanced, max_results=max_results, **kwargs)
