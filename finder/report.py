"""Markdown reports: data/new_today.md and data/review.md."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path


def _line(j: dict) -> str:
    where = ", ".join(j.get("cities") or []) or "; ".join(j["locations"][:2])
    bits = [j["category"], j["type"], j.get("language") or "?", where]
    if j.get("duration"):
        bits.append(j["duration"])
    return f"- [{j['title']}]({j['url']}) - " + " · ".join(b for b in bits if b)


def write_new_today(path: Path, db: dict, new_ids: list[str], run_at: str) -> None:
    jobs = [db["jobs"][i] for i in new_ids]
    shown = [j for j in jobs if j["category"] != "excluded"]
    by_co = defaultdict(list)
    for j in shown:
        by_co[j["company"]].append(j)
    out = [f"# New internship postings ({run_at[:10]})", "",
           f"{len(shown)} new business-relevant postings at {len(by_co)} companies "
           f"({len(jobs) - len(shown)} technical/excluded postings not listed).", ""]
    for co in sorted(by_co, key=str.lower):
        out.append(f"## {co}")
        out += [_line(j) for j in sorted(by_co[co], key=lambda j: j["title"])]
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8")


def write_review(path: Path, db: dict, unclear_location: list[dict], run_at: str) -> None:
    flagged = [j for j in db["jobs"].values() if j["status"] == "open" and j.get("needs_review")]
    out = [f"# Postings needing review ({run_at[:10]})", "",
           "Deterministic rules were not confident about these. They are kept (not dropped);",
           "tune `config.yaml` if a pattern keeps recurring.", "",
           f"## Category uncertain ({len(flagged)})", ""]
    for j in sorted(flagged, key=lambda j: (j["company"].lower(), j["title"])):
        out.append(f"{_line(j)} - **{j['company']}** - _{j.get('review_reason')}_")
    out += ["", f"## Internship, location unclear ({len(unclear_location)})", "",
            "Not counted as Swiss: the feed gives no recognisable location, or only a region such as Europe/DACH.", ""]
    for p in sorted(unclear_location, key=lambda p: (p["company"].lower(), p["title"])):
        out.append(f"- [{p['title']}]({p['url']}) - **{p['company']}** - locations: {p['locations'] or 'none'}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
