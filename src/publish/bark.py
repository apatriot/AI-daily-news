"""Bark push notifications (iOS)."""
from __future__ import annotations

import logging
import os
import sys
from urllib.parse import quote

import httpx

log = logging.getLogger(__name__)


def notify(title: str, body: str, url: str | None = None, key: str | None = None) -> bool:
    key = key or os.getenv("BARK_KEY", "")
    if not key:
        log.info("BARK_KEY not set, skipping push")
        return False
    endpoint = os.getenv("BARK_SERVER", "https://api.day.app").rstrip("/")
    path = f"{endpoint}/{key}/{quote(title)}/{quote(body)}"
    params = {"group": "ai-daily", "level": "active"}
    if url:
        params["url"] = url
    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(path, params=params)
            response.raise_for_status()
        log.info("bark push sent")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("bark push failed: %s", exc)
        return False


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    if "--alert" in sys.argv:
        notify("AI 日报生成失败", "今天的日报没有生成成功，请查看 Actions 日志")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
