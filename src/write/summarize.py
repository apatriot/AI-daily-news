"""Turn a story into Chinese copy for the daily page."""
from __future__ import annotations

import logging
from pathlib import Path

from ..models import Story
from ..util import estimate_read_min, strip_html, truncate
from .llm import LLM

log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[2] / "config" / "prompts" / "write.md"


def _system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return "你是一名中文科技编辑，只输出 JSON。"


def _user_prompt(story: Story) -> str:
    return (
        f"来源：{story.source_name}\n"
        f"标题：{story.title}\n"
        f"原文摘要：{truncate(strip_html(story.summary_raw), 1500)}\n"
    )


def summarize(stories: list[Story], llm: LLM) -> None:
    system = _system_prompt()
    for story in stories:
        data = llm.chat_json(system, _user_prompt(story)) if llm.enabled else None
        if not data:
            _fallback(story)
            continue
        story.title_zh = truncate(str(data.get("title_zh") or story.title), 40)
        story.summary_zh = truncate(str(data.get("summary_zh") or ""), 400)
        points = data.get("key_points") or []
        story.key_points = [truncate(str(p), 40) for p in points if str(p).strip()][:2]
        story.why_matters = truncate(str(data.get("why_matters") or ""), 80)
        tags = data.get("tags") or []
        story.tags = [str(t).strip().lower() for t in tags if str(t).strip()][:4]
        if not story.summary_zh:
            _fallback(story)
        story.read_min = estimate_read_min(story.summary_zh)


def _fallback(story: Story) -> None:
    """No LLM available: ship a conservative, clearly-marked short version."""
    story.title_zh = truncate(story.title, 60)
    story.summary_zh = truncate(strip_html(story.summary_raw), 260) or "（原文暂无摘要，点击查看原文）"
    story.key_points = []
    story.why_matters = ""
    story.read_min = estimate_read_min(story.summary_zh)
    log.info("fallback copy for %s", story.id)
