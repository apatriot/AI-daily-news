"""Region detection: is this story about the Chinese AI scene?

A story counts as 国内 when it is about a Chinese company, city, regulator or
model — not merely because it was published by a Chinese-language outlet.
"""
from __future__ import annotations

from ..models import Story


def _hits(text: str, entities: list[str]) -> int:
    return sum(1 for entity in entities if entity and entity.lower() in text)


def detect_region(title: str, summary: str, source_region: str = "global",
                  cn_entities: list[str] | None = None,
                  foreign_entities: list[str] | None = None) -> str:
    title_l = (title or "").lower()
    text = f"{title} {summary}".lower()
    cn_entities = cn_entities or []
    foreign_entities = foreign_entities or []

    cn_in_title = _hits(title_l, cn_entities)
    foreign_in_title = _hits(title_l, foreign_entities)
    cn_hits = _hits(text, cn_entities)
    foreign_hits = _hits(text, foreign_entities)

    if cn_in_title and not foreign_in_title:
        return "cn"
    if foreign_in_title and not cn_in_title:
        return "global"
    if cn_hits > foreign_hits:
        return "cn"
    if foreign_hits > cn_hits:
        return "global"
    if source_region == "cn" and not foreign_hits:
        return "cn"
    return "global"


def apply_region(story: Story, source_region: str, cn_entities: list[str],
                 foreign_entities: list[str] | None = None) -> Story:
    story.region = detect_region(
        story.title, story.summary_raw, source_region, cn_entities, foreign_entities
    )
    return story
