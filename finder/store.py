"""data/jobs.json: every matching posting ever seen, keyed by provider:token:job_id."""
from __future__ import annotations

import json
import re
from pathlib import Path

CLOSE_AFTER_MISSES = 2


def load(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"generated_at": None, "jobs": {}}


def save(path: Path, db: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    db["jobs"] = dict(sorted(db["jobs"].items()))
    path.write_text(json.dumps(db, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def merge(db: dict, records: list[dict], ok_companies: set[str], today: str, now: str) -> list[str]:
    """Merge this run's matching records into db. Returns ids that are new.

    ok_companies holds "provider:token" keys whose feed was fetched successfully;
    jobs of companies whose fetch failed are left untouched (previous data kept).
    """
    jobs = db["jobs"]
    seen, new = set(), []
    for rec in records:
        seen.add(rec["id"])
        old = jobs.get(rec["id"])
        if old is None:
            new.append(rec["id"])
            jobs[rec["id"]] = {**rec, "first_seen": today, "last_seen": today, "status": "open", "missed": 0}
        else:
            old.update(rec, last_seen=today, status="open", missed=0)
    for jid, job in jobs.items():
        if jid in seen or job["status"] == "closed":
            continue
        if jid.rsplit(":", 1)[0] in ok_companies:
            job["missed"] = job.get("missed", 0) + 1
            if job["missed"] >= CLOSE_AFTER_MISSES:
                job["status"] = "closed"
                job["closed_on"] = today
    db["generated_at"] = now
    return new


def _dup_key(rec: dict) -> tuple:
    norm = lambda x: re.sub(r"\s+", " ", (x or "").strip().lower())  # noqa: E731
    return norm(rec["company"]), norm(rec["title"]), tuple(sorted(norm(l) for l in rec.get("locations") or []))


def dedupe(records: list[dict]) -> tuple[list[dict], set[str]]:
    """Collapse postings identical in company, title and locations.

    Keeps the record with the lowest id (stable across runs) and lists the others
    under "duplicates". Returns (kept records, ids dropped as duplicates).
    """
    groups: dict[tuple, list[dict]] = {}
    for rec in records:
        groups.setdefault(_dup_key(rec), []).append(rec)
    kept, dropped = [], set()
    for group in groups.values():
        group.sort(key=lambda r: r["id"])
        head = dict(group[0])
        head["duplicates"] = [r["id"] for r in group[1:]]
        dropped.update(head["duplicates"])
        kept.append(head)
    return kept, dropped
