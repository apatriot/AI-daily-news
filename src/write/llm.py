"""Minimal OpenAI-compatible LLM client (works with OpenCode Console, DeepSeek, etc.)."""
from __future__ import annotations

import json
import logging
import os
import re

import httpx

log = logging.getLogger(__name__)


class LLM:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 90.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("LLM_BASE_URL")
                         or "https://opencode.ai/inference/openai/v1").rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENCODE_API_KEY") or ""
        self.model = model or os.getenv("LLM_MODEL") or "deepseek-v4.1-flash"
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def chat_json(self, system: str, user: str) -> dict | None:
        if not self.enabled:
            return None
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/chat/completions",
                                       json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            content = data["choices"][0]["message"]["content"]
            return _parse_json(content)
        except Exception as exc:  # noqa: BLE001 - degrade, never crash the daily run
            log.warning("llm call failed (%s): %s", self.model, exc)
            return None


def _parse_json(content: str) -> dict | None:
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None
