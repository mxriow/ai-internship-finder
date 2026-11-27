"""Job description archive: data/descriptions/<provider>/<token>.json, one shard per feed.

Each matching posting's plain-text description is saved the first time it is seen, replaced when a later
run brings a different text, and kept after the posting closes (for interview prep). An empty description
never overwrites a saved one. Kept out of data/jobs.json so that file stays small and its diffs readable;
one shard per feed means a day's changes touch only the feeds whose postings changed.

Shard format (sorted keys, one job per line block):
  {"<job_id>": {"text": "...", "saved": "YYYY-MM-DD", "updated": "YYYY-MM-DD"}}
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

MAX_CHARS = 30000          # a runaway page (whole site as "description") is cut here


def normalise(text: str | None) -> str:
    t = (text or "").replace("\r", "")
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t[:MAX_CHARS]


def _safe(part: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", part) or "_"


def split_id(jid: str) -> tuple[str, str, str]:
    """'greenhouse:stripe:123' -> ('greenhouse', 'stripe', '123'); job ids may contain ':'."""
    provider, token, job = jid.split(":", 2)
    return provider, token, job


class Archive:
    def __init__(self, base: Path):
        self.base = Path(base)
        self._shards: dict[tuple[str, str], dict] = {}
        self._dirty: set[tuple[str, str]] = set()

    def _path(self, provider: str, token: str) -> Path:
        return self.base / _safe(provider) / f"{_safe(token)}.json"

    def _shard(self, provider: str, token: str) -> dict:
        key = (provider, token)
        if key not in self._shards:
            p, data = self._path(provider, token), {}
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except ValueError as e:            # never let a broken shard stop the run
                    log.warning("description shard %s unreadable (%s); starting it fresh", p, e)
            self._shards[key] = data if isinstance(data, dict) else {}
        return self._shards[key]

    def get(self, jid: str) -> str:
        provider, token, job = split_id(jid)
        return (self._shard(provider, token).get(job) or {}).get("text", "")

    def update(self, jid: str, text: str | None, today: str) -> str | None:
        """Save or refresh one description. Returns 'new', 'updated' or None (unchanged / empty)."""
        text = normalise(text)
        if not text:
            return None
        provider, token, job = split_id(jid)
        shard = self._shard(provider, token)
        old = shard.get(job)
        if old and old.get("text") == text:
            return None
        shard[job] = {"text": text, "saved": (old or {}).get("saved", today), "updated": today}
        self._dirty.add((provider, token))
        return "updated" if old else "new"

    def remove(self, jid: str) -> None:
        provider, token, job = split_id(jid)
        if self._shard(provider, token).pop(job, None) is not None:
            self._dirty.add((provider, token))

    def all_for(self, ids) -> dict[str, str]:
        out = {}
        for jid in ids:
            t = self.get(jid)
            if t:
                out[jid] = t
        return out

    def save(self) -> int:
        for provider, token in sorted(self._dirty):
            p = self._path(provider, token)
            p.parent.mkdir(parents=True, exist_ok=True)
            data = dict(sorted(self._shards[(provider, token)].items()))
            p.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        n, self._dirty = len(self._dirty), set()
        return n
