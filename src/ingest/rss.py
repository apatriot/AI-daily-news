"""RSS ingestion."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
import httpx

from ..models import RawItem
from ..util import canonical_url, strip_html, truncate

log = logging.getLogger(__name__)

USER_AGENT = "ai-daily/0.1 (+https://github.com/apatriot/AI-daily-news)"


def _entry_datetime(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    return None


def fetch_source(source: dict, timeout: float = 20.0) -> list[RawItem]:
    url = source["url"]
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True,
                          headers={"User-Agent": USER_AGENT}) as client:
            response = client.get(url)
            response.raise_for_status()
            parsed = feedparser.parse(response.content)
    except Exception as exc:  # noqa: BLE001 - one bad feed must not kill the run
        log.warning("feed failed: %s (%s)", source["id"], exc)
        return []

    items: list[RawItem] = []
    for entry in parsed.entries:
        published = _entry_datetime(entry)
        if not published:
            continue
        link = entry.get("link") or ""
        if not link:
            continue
        summary = entry.get("summary") or entry.get("description") or ""
        items.append(
            RawItem(
                title=strip_html(entry.get("title") or "").strip(),
                url=canonical_url(link),
                source_id=source["id"],
                source_name=source["name"],
                category=source.get("category", "industry"),
                published=published,
                summary_raw=truncate(strip_html(summary), 1200),
                weight=float(source.get("weight", 0.5)),
            )
        )
    log.info("feed ok: %s -> %d items", source["id"], len(items))
    return items
