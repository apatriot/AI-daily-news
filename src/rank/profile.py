"""Interest profile: defaults, loading, and (later) feedback updates."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


@dataclass
class Profile:
    clusters: dict[str, dict] = field(default_factory=dict)
    sources: dict = field(default_factory=dict)
    source_quality: dict[str, float] = field(default_factory=dict)
    exclusions: list[str] = field(default_factory=list)
    style: dict = field(default_factory=dict)
    exploration: dict = field(default_factory=dict)
    updated: str | None = None
    version: int = 1

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        path = Path(path)
        if not path.exists():
            log.warning("profile not found at %s, using empty profile", path)
            return cls()
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__ if k in data})

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__ if k in data})

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "updated": self.updated,
            "clusters": self.clusters,
            "sources": self.sources,
            "source_quality": self.source_quality,
            "exclusions": self.exclusions,
            "style": self.style,
            "exploration": self.exploration,
        }

    # -- weights ---------------------------------------------------------
    def cluster_weight(self, cluster: str) -> float:
        return float(self.clusters.get(cluster, {}).get("weight", 0.1))

    def subtopic_weight(self, cluster: str, subtopic: str) -> float | None:
        subs = self.clusters.get(cluster, {}).get("subtopics") or {}
        if subtopic in subs:
            return float(subs[subtopic])
        return None

    def source_boost(self, source_id: str) -> float:
        boost = (self.sources or {}).get("boost") or []
        mute = (self.sources or {}).get("mute") or []
        if source_id in mute:
            return 0.0
        return 1.12 if source_id in boost else 1.0

    def quality(self, source_id: str) -> float:
        # Bayesian-ish default: unknown sources are treated as 0.75
        return float(self.source_quality.get(source_id, 0.75))

    def cold_clusters(self) -> list[str]:
        return list((self.exploration or {}).get("cold_clusters") or [])

    def is_excluded(self, story_text: str) -> bool:
        text = story_text.lower()
        return any(word.lower() in text for word in self.exclusions)
