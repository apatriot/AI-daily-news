from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.models import RawItem, Story
from src.process.cluster import build_stories, classify
from src.rank.profile import Profile
from src.rank.select import select
from src.util import canonical_url, story_id, strip_html


def item(title, url, source="a", weight=0.8, hours_ago=1):
    return RawItem(
        title=title,
        url=url,
        source_id=source,
        source_name=source.upper(),
        category="industry",
        published=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        summary_raw="summary " + title,
        weight=weight,
    )


class UtilTest(unittest.TestCase):
    def test_canonical_url_strips_tracking(self):
        url = "https://Example.com/a/?utm_source=x&id=3#frag"
        self.assertEqual(canonical_url(url), "https://example.com/a?id=3")

    def test_story_id_stable(self):
        self.assertEqual(story_id("https://a.com/x?utm_source=1"), story_id("https://a.com/x"))

    def test_strip_html(self):
        self.assertEqual(strip_html("<p>Hello <b>world</b></p>"), "Hello world")


class ClusterTest(unittest.TestCase):
    def test_similar_titles_merge(self):
        items = [
            item("OpenAI releases GPT-6", "https://a.com/1", "a"),
            item("OpenAI releases GPT-6!", "https://b.com/1", "b"),
            item("Something completely different", "https://c.com/1", "c"),
        ]
        stories = build_stories(items)
        self.assertEqual(len(stories), 2)
        merged = [s for s in stories if len(s.related) == 1]
        self.assertEqual(len(merged), 1)

    def test_classify_by_keywords(self):
        story = Story(
            id="x", title="New open source model weights released",
            url="https://a.com", source_id="a", source_name="A",
            category="industry", published=datetime.now(timezone.utc),
            summary_raw="github weights quantization",
        )
        classify(story, {
            "oss": {"keywords": ["open source", "weights"], "subtopics": {"open-model": ["weights"]}},
            "industry": {"keywords": ["funding"], "subtopics": {}},
        })
        self.assertEqual(story.cluster, "oss")
        self.assertEqual(story.subtopic, "open-model")


class SelectTest(unittest.TestCase):
    def setUp(self):
        self.profile = Profile(clusters={
            "frontier": {"weight": 0.4, "subtopics": {"research": 0.4}},
            "product": {"weight": 0.3, "subtopics": {"agents": 0.3}},
            "industry": {"weight": 0.2, "subtopics": {}},
            "oss": {"weight": 0.1, "subtopics": {}},
        })
        self.now = datetime.now(timezone.utc)
        self.stories = []
        for i in range(20):
            cluster = ["frontier", "product", "industry", "oss"][i % 4]
            s = Story(
                id=f"s{i}", title=f"Story {i}", url=f"https://a.com/{i}",
                source_id=f"src{i % 6}", source_name=f"S{i % 6}",
                category=cluster, published=self.now - timedelta(hours=i),
                summary_raw="x" * 300, cluster=cluster,
            )
            s.scores["authority"] = 0.8
            s.summary_zh = "摘要" * 100
            self.stories.append(s)

    def test_quotas_filled(self):
        sections = select(self.stories, self.profile, self.now)
        self.assertEqual(len(sections["headline"]), 1)
        self.assertEqual(len(sections["personal"]), 3)
        self.assertEqual(len(sections["global"]), 2)
        self.assertEqual(len(sections["explore"]), 1)
        self.assertEqual(len(sections["deep"]), 1)
        self.assertEqual(len(sections["briefs"]), 5)

    def test_no_duplicate_story_across_sections(self):
        sections = select(self.stories, self.profile, self.now)
        ids = [s.id for name, items in sections.items() if name != "briefs" for s in items]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
