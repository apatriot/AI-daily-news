"""Static site rendering."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models import Story
from ..util import truncate

log = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _human_time(published: datetime, now: datetime) -> str:
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    hours = max(0.0, (now - published).total_seconds() / 3600)
    if hours < 1:
        return "刚刚"
    if hours < 24:
        return f"{int(hours)} 小时前"
    return f"{int(hours // 24)} 天前"


def _tldr(sections: dict[str, list[Story]]) -> list[str]:
    lines: list[str] = []
    pool = sections.get("headline", []) + sections.get("global", []) + sections.get("personal", [])
    for story in pool:
        if len(lines) >= 3:
            break
        text = story.why_matters or story.summary_zh or ""
        if not text or text.startswith("（原文暂无摘要"):
            text = story.title_zh or story.title
        lines.append(truncate(text, 42))
    return lines


def render(
    sections: dict[str, list[Story]],
    *,
    date: datetime,
    out_dir: Path,
    assets_dir: Path,
    site_url: str = "",
    feedback_url: str = "",
    stats: dict | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    assets_out = out_dir / "assets"
    if assets_out.exists():
        shutil.rmtree(assets_out)
    shutil.copytree(assets_dir, assets_out)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    now = datetime.now(timezone.utc)
    date_key = date.strftime("%Y-%m-%d")
    date_label = f"{date.year}年{date.month}月{date.day}日 · {WEEKDAYS[date.weekday()]}"

    cards = {name: items for name, items in sections.items()}
    total_cards = sum(len(v) for k, v in cards.items() if k != "briefs")
    reading = sum(s.read_min for k, v in cards.items() if k != "briefs" for s in v)

    def ctx(root: str, page: str = "index", story_id: str = "") -> dict:
        return {
            "root": root,
            "page": page,
            "story_id": story_id,
            "date_key": date_key,
            "date_label": date_label,
            "tldr": _tldr(sections),
            "sections": cards,
            "total_cards": total_cards,
            "reading_min": max(1, reading),
            "feedback_url": feedback_url,
            "site_url": site_url,
            "human_time": lambda d: _human_time(d, now),
            "stats": stats or {},
        }

    index_html = env.get_template("index.html").render(**ctx(""))
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")

    # detail pages
    detail_dir = out_dir / "s"
    detail_dir.mkdir(exist_ok=True)
    detail_tpl = env.get_template("story.html")
    seen_ids: set[str] = set()
    for name, items in cards.items():
        for story in items:
            if story.id in seen_ids:
                continue
            seen_ids.add(story.id)
            html = detail_tpl.render(story=story, **ctx("../", page="story", story_id=story.id))
            (detail_dir / f"{story.id}.html").write_text(html, encoding="utf-8")

    # archive (re-render with ../ so relative links resolve from /archive/)
    archive_dir = out_dir / "archive"
    archive_dir.mkdir(exist_ok=True)
    archive_html = env.get_template("index.html").render(**ctx("../"))
    (archive_dir / f"{date_key}.html").write_text(archive_html, encoding="utf-8")
    dates = sorted((p.stem for p in archive_dir.glob("*.html") if p.stem != "index"), reverse=True)
    archive_tpl = env.get_template("archive.html")
    (archive_dir / "index.html").write_text(
        archive_tpl.render(**ctx("../"), dates=dates), encoding="utf-8"
    )

    manifest = {
        "name": "AI 日报",
        "short_name": "AI 日报",
        "start_url": "./",
        "display": "standalone",
        "background_color": "#fafaf9",
        "theme_color": "#0f766e",
        "icons": [{"src": "assets/icon.png", "sizes": "512x512", "type": "image/png"}],
    }
    (out_dir / "manifest.webmanifest").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("rendered %d cards to %s", total_cards, out_dir)
