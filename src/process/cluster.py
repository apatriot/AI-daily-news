"""Cluster near-duplicate items into stories and classify them."""
from __future__ import annotations

import logging
from difflib import SequenceMatcher

from ..models import RawItem, Story
from ..util import story_id, truncate

log = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.82


def _normalize_title(title: str) -> str:
    return "".join(ch.lower() for ch in title if ch.isalnum() or ch.isspace())


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize_title(a), _normalize_title(b)).ratio()


def build_stories(items: list[RawItem]) -> list[Story]:
    """Group items that describe the same event, keeping the best source as primary."""
    items = sorted(items, key=lambda i: (i.weight, i.published), reverse=True)
    stories: list[Story] = []
    by_url: dict[str, Story] = {}

    for item in items:
        if item.url in by_url:
            continue
        match = None
        for story in stories:
            if _similar(item.title, story.title) >= SIMILARITY_THRESHOLD:
                match = story
                break
        if match is None:
            story = Story(
                id=story_id(item.url),
                title=item.title,
                url=item.url,
                source_id=item.source_id,
                source_name=item.source_name,
                category=item.category,
                published=item.published,
                summary_raw=item.summary_raw,
                cluster=item.category,
            )
            stories.append(story)
            by_url[item.url] = story
            continue

        by_url[item.url] = match
        if item.source_id != match.source_id:
            match.related.append({
                "source": item.source_name,
                "url": item.url,
                "title": item.title,
            })
        # Prefer the richer summary among duplicates.
        if len(item.summary_raw) > len(match.summary_raw):
            match.summary_raw = item.summary_raw

    log.info("clustered %d items into %d stories", len(items), len(stories))
    return stories


def classify(story: Story, rules: dict) -> Story:
    """Assign cluster/subtopic from keyword rules (used before/without LLM)."""
    text = f"{story.title} {story.summary_raw}".lower()
    best_cluster, best_hits = story.cluster or "industry", 0
    best_sub, best_sub_hits = "", 0

    for cluster, rule in (rules or {}).items():
        hits = sum(1 for kw in rule.get("keywords", []) if kw.lower() in text)
        if hits > best_hits:
            best_cluster, best_hits = cluster, hits
        for sub, keywords in (rule.get("subtopics") or {}).items():
            sub_hits = sum(1 for kw in keywords if kw.lower() in text)
            if sub_hits > best_sub_hits:
                best_sub, best_sub_hits = sub, sub_hits

    story.cluster = best_cluster
    story.subtopic = best_sub
    story.tags = [t for t in {best_cluster, best_sub} if t]
    story.summary_raw = truncate(story.summary_raw, 1200)
    return story
