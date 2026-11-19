"""Bark push notifications (iOS).

Bark's recommended way to push is a JSON POST to ``/push``; the GET path form
breaks on long bodies and hides the server's error message, so we use POST and
surface the response body when something is wrong.
"""
from __future__ import annotations

import logging
import os
import sys

import httpx

log = logging.getLogger(__name__)


def notify(title: str, body: str, url: str | None = None, key: str | None = None) -> bool:
    key = (key or os.getenv("BARK_KEY", "")).strip()
    if not key:
        log.info("BARK_KEY not set, skipping push")
        return False

    endpoint = os.getenv("BARK_SERVER", "https://api.day.app").rstrip("/")
    payload = {
        "device_key": key,
        "title": title,
        "body": body,
        "group": "ai-daily",
        "level": "active",
        "icon": os.getenv("BARK_ICON", ""),
    }
    if url:
        payload["url"] = url
    payload = {k: v for k, v in payload.items() if v}

    try:
        with httpx.Client(timeout=15) as client:
            response = client.post(f"{endpoint}/push", json=payload)
        if response.status_code >= 400:
            log.warning(
                "bark push failed: HTTP %s %s",
                response.status_code,
                response.text[:300],
            )
            return False
        data = response.json() if response.content else {}
        if isinstance(data, dict) and data.get("code") not in (None, 200):
            log.warning("bark push rejected: %s", str(data)[:300])
            return False
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
