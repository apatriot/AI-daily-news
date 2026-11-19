"""Fetch article body text for stories whose feed summary is useless."""
from __future__ import annotations

import logging
import re

import httpx

from ..models import Story
from ..util import strip_html, truncate

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; ai-daily/0.1)"
USELESS = ("点击查看原文", "查看原文", "阅读全文", "查看更多", "read more", "continue reading")
MIN_USEFUL = 120


def _useless(summary: str) -> bool:
    text = (summary or "").strip()
    if len(text) < MIN_USEFUL:
        return True
    return any(marker in text.lower() for marker in USELESS)


def _extract(html_text: str) -> str:
    html_text = re.sub(r"(?is)<(script|style|noscript|nav|footer|header)[^>]*>.*?</\1>", " ", html_text)
    blocks = re.findall(r"(?is)<p[^>]*>(.*?)</p>", html_text)
    paragraphs = [strip_html(block) for block in blocks]
    paragraphs = [p for p in paragraphs if len(p) >= 30]
    return truncate("\n".join(paragraphs[:20]), 4000)


def enrich(stories: list[Story], timeout: float = 12.0) -> None:
    targets = [s for s in stories if _useless(s.summary_raw)]
    if not targets:
        return
    log.info("enriching %d stories with thin feed summaries", len(targets))
    with httpx.Client(timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": USER_AGENT}) as client:
        for story in targets:
            try:
                response = client.get(story.url)
                response.raise_for_status()
                text = _extract(response.text)
            except Exception as exc:  # noqa: BLE001
                log.debug("enrich failed for %s: %s", story.url, exc)
                continue
            if len(text) >= MIN_USEFUL:
                story.summary_raw = text
                log.info("enriched %s -> %d chars", story.id, len(text))
