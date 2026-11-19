"""Pipeline entry point: python -m src.run"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .ingest.rss import fetch_source
from .models import RawItem
from .process.cluster import build_stories, classify
from .publish.bark import notify
from .rank.profile import Profile
from .rank.select import select
from .render.site import render
from .util import now_utc
from .write.llm import LLM
from .write.summarize import summarize

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
ASSETS_DIR = ROOT / "assets"
SEEN_PATH = DATA_DIR / "seen.json"
SEEN_TTL_DAYS = 14

log = logging.getLogger("ai-daily")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def local_today() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:  # noqa: BLE001
        return datetime.now(timezone(timedelta(hours=8)))


def load_seen() -> dict[str, str]:
    if not SEEN_PATH.exists():
        return {}
    try:
        data = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
        return dict(data.get("items") or {})
    except (json.JSONDecodeError, OSError):
        return {}


def save_seen(seen: dict[str, str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(
        json.dumps({"items": seen}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def collect(sources: list[dict], limit: int | None = None) -> list[RawItem]:
    items: list[RawItem] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for batch in pool.map(fetch_source, sources):
            items.extend(batch)
    log.info("collected %d raw items", len(items))
    if limit:
        items = items[:limit]
    return items


def filter_window(items: list[RawItem], now: datetime, days: int = 7) -> list[RawItem]:
    floor = now - timedelta(days=days)
    kept = [i for i in items if floor <= i.published <= now + timedelta(hours=2)]
    log.info("window filter: %d -> %d", len(items), len(kept))
    return kept


def drop_seen(stories, seen: dict[str, str]) -> list:
    cutoff = now_utc() - timedelta(days=SEEN_TTL_DAYS)
    fresh = []
    for story in stories:
        stamp = seen.get(story.id)
        if stamp:
            try:
                if datetime.fromisoformat(stamp) > cutoff:
                    continue
            except ValueError:
                pass
        fresh.append(story)
    log.info("seen filter: %d -> %d", len(stories), len(fresh))
    return fresh


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description="Generate the AI daily digest")
    parser.add_argument("--date", help="report date YYYY-MM-DD (default: today in Asia/Shanghai)")
    parser.add_argument("--limit", type=int, help="max raw items (debug)")
    parser.add_argument("--offline", action="store_true", help="skip LLM even if a key exists")
    args = parser.parse_args(argv)

    today = local_today()
    if args.date:
        today = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=today.tzinfo)

    sources_cfg = load_yaml(CONFIG_DIR / "sources.yaml")
    sources = sources_cfg.get("sources") or []
    rules = sources_cfg.get("keyword_rules") or {}

    profile_path = Path(os.getenv("PROFILE_PATH") or CONFIG_DIR / "profile.default.yaml")
    profile = Profile.load(profile_path)

    now = now_utc()
    items = filter_window(collect(sources, args.limit), now, days=7)
    if not items:
        log.error("no items collected — aborting without touching the site")
        return 2

    stories = build_stories(items)
    for story in stories:
        classify(story, rules)
        story.scores["authority"] = next(
            (s.get("weight", 0.5) for s in sources if s["id"] == story.source_id), 0.5
        )

    seen = load_seen()
    stories = drop_seen(stories, seen)
    if not stories:
        log.warning("every story was already published — nothing to do")
        return 0

    llm = LLM()
    if args.offline:
        llm.api_key = ""
    log.info("LLM enabled=%s model=%s", llm.enabled, llm.model)
    summarize(stories, llm)

    sections = select(stories, profile, now)

    feedback_url = os.getenv("FEEDBACK_POST_URL", "")
    site_url = os.getenv("SITE_URL", "")
    stats = {
        "raw": len(items),
        "stories": len(stories),
        "model": llm.model if llm.enabled else "offline",
    }
    render(
        sections,
        date=today,
        out_dir=DOCS_DIR,
        assets_dir=ASSETS_DIR,
        site_url=site_url,
        feedback_url=feedback_url,
        stats=stats,
    )

    # persist artefacts
    date_key = today.strftime("%Y-%m-%d")
    stories_dir = DATA_DIR / "stories"
    stories_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": date_key,
        "generated_at": now.isoformat(),
        "sections": {name: [s.to_public() for s in items] for name, items in sections.items()},
        "stats": stats,
    }
    (stories_dir / f"{date_key}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    stamp = now_utc().isoformat()
    for story in stories:
        seen[story.id] = stamp
    save_seen(seen)

    if os.getenv("BARK_KEY"):
        notify(
            "AI 日报",
            f"{date_key} 已更新 · {sum(len(v) for k, v in sections.items() if k != 'briefs')} 条",
            url=site_url or None,
        )

    log.info("done: %s", date_key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
