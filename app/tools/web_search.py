"""联网搜索工具（对应 Java WebSearchTool / WebScrapingTool）。"""
from __future__ import annotations
import httpx
from langchain_core.tools import tool
from app.config import settings


@tool
def search_web(query: str) -> str:
    """使用 Serper.dev Google Search API 查询最新资讯。query 应为简单关键词。"""
    if not settings.search_api_key:
        return "未配置 SEARCH_API_KEY，无法联网搜索。查询: {}".format(query)
    try:
        resp = httpx.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": 5},
            headers={"X-API-KEY": settings.search_api_key, "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("organic", [])[:5]:
            title = item.get("title", "").strip()
            link = item.get("link", "").strip()
            snippet = item.get("snippet", "").strip()
            if title or snippet:
                results.append("{}\n{}\n{}".format(title, snippet, link).strip())
        if not results:
            return "未搜索到相关结果: {}".format(query)
        return "搜索结果：\n\n" + "\n\n".join(results)
    except Exception as e:
        return "联网搜索失败: {}".format(e)


@tool
def scrape_web_page(url: str) -> str:
    """抓取指定网页的文本内容。"""
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:3000]
    except Exception as e:
        return "网页抓取失败: {}".format(e)


search_tools = [search_web, scrape_web_page]
