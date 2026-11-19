"""Score stories and select the daily quota."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from ..models import Story
from ..util import estimate_read_min
from .profile import Profile

log = logging.getLogger(__name__)

SECTION_QUOTAS = {
    "headline": 1,
    "personal": 3,
    "global": 2,
    "explore": 1,
    "deep": 1,
}
BRIEF_COUNT = 5
CN_RATIO = 0.5


def _hours_since(published: datetime, now: datetime) -> float:
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return max(0.0, (now - published).total_seconds() / 3600)


def score_story(story: Story, profile: Profile, now: datetime) -> dict[str, float]:
    sub = profile.subtopic_weight(story.cluster, story.subtopic)
    if sub is None:
        relevance = profile.cluster_weight(story.cluster)
    else:
        relevance = 0.6 * profile.cluster_weight(story.cluster) + 0.4 * sub

    authority = story.scores.get("authority", 0.6)
    coverage = min(len(story.related), 3) / 3
    importance = 0.6 * authority + 0.4 * coverage

    hours = _hours_since(story.published, now)
    novelty = math.exp(-hours / 48.0)
    explore = 1.0 if story.cluster in profile.cold_clusters() else 0.0

    final = (
        0.45 * relevance
        + 0.25 * importance
        + 0.20 * novelty
        + 0.10 * explore
    )
    final *= profile.source_boost(story.source_id)
    final *= 0.85 + 0.15 * profile.quality(story.source_id)
    final *= story.scores.get("quality_penalty", 1.0)

    return {
        "relevance": round(relevance, 3),
        "importance": round(importance, 3),
        "novelty": round(novelty, 3),
        "explore": explore,
        "final": round(final, 3),
    }


def _pick(pool: list[Story], key: str, count: int, chosen: list[Story],
          max_per_cluster: int = 2, max_per_source: int = 1,
          cn_bonus: float = 0.0) -> list[Story]:
    def rank(story: Story) -> float:
        return story.scores.get(key, 0.0) + (cn_bonus if story.region == "cn" else 0.0)

    picked: list[Story] = []
    for story in sorted(pool, key=rank, reverse=True):
        if story in chosen or story in picked:
            continue
        if sum(1 for s in chosen + picked if s.cluster == story.cluster) >= max_per_cluster:
            continue
        if sum(1 for s in chosen + picked if s.source_id == story.source_id) >= max_per_source:
            continue
        picked.append(story)
        if len(picked) >= count:
            break
    return picked


def select(stories: list[Story], profile: Profile, now: datetime) -> dict[str, list[Story]]:
    for story in stories:
        story.scores.update(score_story(story, profile, now))
        story.read_min = estimate_read_min(story.summary_zh or story.summary_raw)

    stories = [s for s in stories if not profile.is_excluded(f"{s.title} {s.summary_raw}")]
    stories.sort(key=lambda s: s.scores["final"], reverse=True)

    sections: dict[str, list[Story]] = {name: [] for name in SECTION_QUOTAS}
    chosen: list[Story] = []

    def need_cn() -> bool:
        picked = len(chosen)
        cn = sum(1 for s in chosen if s.region == "cn")
        return cn < math.ceil(picked * CN_RATIO)

    sections["headline"] = _pick(stories, "final", SECTION_QUOTAS["headline"], chosen,
                                 max_per_cluster=9, max_per_source=9)
    chosen += sections["headline"]

    sections["personal"] = _pick(stories, "relevance", SECTION_QUOTAS["personal"], chosen,
                                 cn_bonus=0.12 if need_cn() else 0.0)
    chosen += sections["personal"]

    # Global ignores personal relevance entirely: rank by importance only.
    sections["global"] = _pick(stories, "importance", SECTION_QUOTAS["global"], chosen,
                               max_per_cluster=3, max_per_source=2,
                               cn_bonus=0.12 if need_cn() else 0.0)
    chosen += sections["global"]

    sections["explore"] = _pick(stories, "explore", SECTION_QUOTAS["explore"], chosen,
                                max_per_cluster=9, max_per_source=9,
                                cn_bonus=0.12 if need_cn() else 0.0)
    chosen += sections["explore"]

    deep_pool = [s for s in stories if s.cluster in ("frontier", "oss")]
    sections["deep"] = _pick(deep_pool or stories, "final", SECTION_QUOTAS["deep"], chosen,
                             max_per_cluster=9, max_per_source=9,
                             cn_bonus=0.12 if need_cn() else 0.0)
    chosen += sections["deep"]

    cn_bonus = 0.12 if need_cn() else 0.0
    remaining = sorted(
        (s for s in stories if s not in chosen),
        key=lambda s: s.scores.get("final", 0.0) + (cn_bonus if s.region == "cn" else 0.0),
        reverse=True,
    )
    sections["briefs"] = remaining[:BRIEF_COUNT]

    _rebalance_region(sections, stories, profile, ratio=CN_RATIO)

    for name, items in sections.items():
        for story in items:
            story.section = name
            if not story.why_for_you:
                story.why_for_you = _why_for_you(story, profile, name)

    log.info("selected: %s", {k: len(v) for k, v in sections.items()})
    return sections


def _rebalance_region(sections: dict[str, list[Story]], pool: list[Story],
                      profile: Profile, ratio: float = CN_RATIO) -> None:
    """Guarantee at least `ratio` of displayed items are China-related."""
    displayed = [s for items in sections.values() for s in items]
    if not displayed:
        return

    used = {id(s) for s in displayed}
    candidates = sorted(
        [s for s in pool if s.region == "cn" and id(s) not in used],
        key=lambda s: s.scores.get("final", 0.0),
        reverse=True,
    )

    need = math.ceil(len(displayed) * ratio) - sum(1 for s in displayed if s.region == "cn")
    # Replace non-cn items in the least disruptive order; headline stays untouched.
    for name in ("briefs", "global", "explore", "deep", "personal"):
        items = sections.get(name) or []
        for index in range(len(items) - 1, -1, -1):
            if need <= 0 or not candidates:
                break
            if items[index].region == "cn":
                continue
            replacement = candidates.pop(0)
            replacement.section = name
            replacement.why_for_you = _why_for_you(replacement, profile, name)
            items[index] = replacement
            need -= 1

    # Still short: drop non-cn items (tail sections first) so the ratio holds.
    for name in ("briefs", "deep", "explore", "global", "personal"):
        while True:
            total = sum(len(v) for v in sections.values())
            cn = sum(1 for items in sections.values() for s in items if s.region == "cn")
            if total == 0 or cn * 2 >= total:
                return
            items = sections.get(name) or []
            drop = next((i for i in range(len(items) - 1, -1, -1)
                         if items[i].region != "cn"), None)
            if drop is None:
                break
            items.pop(drop)


def _why_for_you(story: Story, profile: Profile, section: str) -> str:
    cluster_name = {
        "frontier": "模型与前沿研究",
        "product": "产品与工具",
        "industry": "行业与商业",
        "oss": "开源与工程实践",
    }.get(story.cluster, "AI")
    if section == "personal":
        return f"你近期常读「{cluster_name}」相关内容"
    if section == "global":
        return "行业全局：与你兴趣无关，但值得知道"
    if section == "explore":
        return f"探索：你最近 30 天没怎么看「{cluster_name}」"
    if section == "deep":
        return "技术深度：适合细读"
    return "今日综合热度最高"
