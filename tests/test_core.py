from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.models import RawItem, Story
from src.process.cluster import build_stories, classify
from src.process.filter import is_ai_related, is_noise
from src.process.region import detect_region
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


class FilterTest(unittest.TestCase):
    def test_event_signup_is_noise(self):
        self.assertTrue(is_noise("创新大会嘉宾阵容更新", "", ["嘉宾阵容", "报名"]))

    def test_real_news_is_not_noise(self):
        self.assertFalse(is_noise("OpenAI 发布新模型", "性能提升 30%", ["报名", "嘉宾阵容"]))

    def test_ai_keyword_match(self):
        self.assertTrue(is_ai_related("大模型推理优化", "", ["大模型", "推理"]))
        self.assertFalse(is_ai_related("新款手机发布", "价格 3999", ["大模型", "推理"]))


class RegionTest(unittest.TestCase):
    def test_cn_source_is_cn(self):
        self.assertEqual(detect_region("Anything", "", "cn", []), "cn")

    def test_cn_entity_in_english_text(self):
        self.assertEqual(
            detect_region("Alibaba launches new Qwen model", "", "global", ["阿里", "qwen"]),
            "cn",
        )

    def test_chinese_text_is_cn(self):
        self.assertEqual(
            detect_region("字节跳动发布新模型", "这是一个测试", "global", ["字节"]),
            "cn",
        )

    def test_cn_source_covering_foreign_company_is_global(self):
        self.assertEqual(
            detect_region(
                "Anthropic 发布新模型", "Claude 能力提升", "cn",
                ["字节", "阿里"], ["anthropic", "claude"],
            ),
            "global",
        )

    def test_global_story(self):
        self.assertEqual(
            detect_region("OpenAI ships a new model", "It is fast.", "global", ["阿里", "qwen"]),
            "global",
        )


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
                region="cn" if i % 2 == 0 else "global",
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

    def test_cn_ratio_at_least_half(self):
        sections = select(self.stories, self.profile, self.now)
        items = [s for group in sections.values() for s in group]
        cn = sum(1 for s in items if s.region == "cn")
        self.assertGreaterEqual(cn * 2, len(items))

    def test_cn_ratio_with_scarce_cn_pool(self):
        for index, story in enumerate(self.stories):
            story.region = "cn" if index < 3 else "global"
        sections = select(self.stories, self.profile, self.now)
        items = [s for group in sections.values() for s in group]
        cn = sum(1 for s in items if s.region == "cn")
        self.assertGreaterEqual(cn * 2, len(items))

    def test_no_duplicate_story_across_sections(self):
        sections = select(self.stories, self.profile, self.now)
        ids = [s.id for name, items in sections.items() if name != "briefs" for s in items]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
