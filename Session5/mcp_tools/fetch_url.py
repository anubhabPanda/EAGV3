"""
Fetch URL Tool

Fetches clean markdown from a URL using crawl4ai with headless Chromium.
This is essential for reading content from URLs after web searches.
"""

import os
from typing import Dict, Any


async def fetch_url(url: str, timeout: int = 20) -> Dict[str, Any]:
    """
    Fetch clean markdown from a URL via crawl4ai (headless Chromium).
    
    After a web search, this tool MUST be used to read the content from URLs.
    Search results only contain snippets - this tool fetches the full content.

    Args:
        url: The URL to fetch
        timeout: Timeout in seconds (default 20)

    Returns:
        {
            "status": int,
            "content_type": str,
            "length_bytes": int,
            "text": str  # Clean markdown content
        }

    Primary Library:
        - crawl4ai (AsyncWebCrawler with headless Chromium)

    Example:
        result = await fetch_url("https://en.wikipedia.org/wiki/Evolution")
        print(result["text"])  # Clean markdown content
    """
    from crawl4ai import AsyncWebCrawler

    # crawl4ai uses Rich which writes via its own captured stdout reference, so
    # contextlib.redirect_stdout doesn't catch it. Redirect at the file-descriptor
    # level — crawl4ai's banner / [FETCH] / [SCRAPE] markers would otherwise
    # corrupt the MCP stdio JSON-RPC stream.
    saved_fd = os.dup(1)
    os.dup2(2, 1)
    try:
        async with AsyncWebCrawler(verbose=False) as crawler:
            r = await crawler.arun(url=url)
    finally:
        os.dup2(saved_fd, 1)
        os.close(saved_fd)

    # r.markdown is a str subclass (StringCompatibleMarkdown) that Pydantic
    # serializes as {} because its real field is private. Pull the raw string
    # out and force a plain str so FastMCP serializes correctly.
    md = r.markdown
    raw = (
        getattr(md, "raw_markdown", None)
        or getattr(md, "fit_markdown", None)
        or md
        or r.cleaned_html
        or r.html
        or ""
    )
    text = str(raw)

    return {
        "status": int(getattr(r, "status_code", None) or 200),
        "content_type": "text/markdown",
        "length_bytes": len(text.encode("utf-8")),
        "text": text,
    }
