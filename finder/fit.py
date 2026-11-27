"""Best-fit score (0-105) for one posting, from the points in config.yaml `fit_score`.

Five parts, each worth its configured points:
  degree    bachelor OK > unclear > master's/MBA required
  language  English only / English required > needs German > needs French or Dutch
  category  brand, marketing, commercial, e-commerce > sales, strategy, insights > other business
  start     in or after the cut-off month (`early_start_before`), or unclear > earlier or ASAP
  duration  3-6 months > unclear > shorter > longer
  + a small bonus for higher stated pay (so the maximum is 105)
"""
from __future__ import annotations

import re

DEFAULT = {
    "degree": {"bachelor_ok": 25, "unclear": 15, "master_required": 0},
    "language": {"english": 25, "german": 10, "french_dutch": 5},
    "category": {"points": {"top": 25, "middle": 15, "other": 5},
                 "top": ["brand", "marketing", "commercial", "ecommerce_digital"],
                 "middle": ["sales", "strategy", "marketing_analytics"]},
    "start": {"from_cutoff_or_unclear": 15, "earlier": 0},
    "duration": {"three_to_six_months": 10, "unclear": 6, "shorter": 4, "longer": 0},
    "pay_bonus": [[2000, 5], [1500, 3], [1000, 1]],   # [gross EUR/month at least, extra points]
}


def duration_months(text: str | None) -> float | None:
    """'6-month' -> 6, '4-6 Monate' -> 6 (the upper end), '15 week' -> 3.5, None if not stated."""
    if not text:
        return None
    nums = [int(n) for n in re.findall(r"\d{1,2}", text)]
    if not nums:
        return None
    n = max(nums)
    if re.search(r"week|woche|semaine|settimane|weken", text, re.I):
        return round(n / 4.33, 1)
    return float(n)


def language_need(job: dict) -> str:
    """english | german | french_dutch: the most demanding non-English language the role needs."""
    need = set(job.get("lang_required") or [])
    lang = job.get("language")
    if need & {"FR", "NL"} or lang in ("FR", "NL"):
        return "french_dutch"
    if "DE" in need or lang == "DE":
        return "german"
    return "english"


def score(job: dict, cfg: dict | None = None, early_before: str | None = None) -> int:
    c = {**DEFAULT, **(cfg or {})}
    pts = c["degree"].get(job.get("degree") or "unclear", c["degree"]["unclear"])
    pts += c["language"][language_need(job)]
    cat, cp = job.get("category"), c["category"]
    pts += cp["points"]["top"] if cat in cp["top"] else cp["points"]["middle"] if cat in cp["middle"] else (
        0 if cat in (None, "excluded") else cp["points"]["other"])
    early = job.get("start_asap") or (early_before and job.get("start_month") and job["start_month"] < early_before)
    pts += c["start"]["earlier"] if early else c["start"]["from_cutoff_or_unclear"]
    months = duration_months(job.get("duration"))
    d = c["duration"]
    pts += d["unclear"] if months is None else d["three_to_six_months"] if 3 <= months <= 6 else (
        d["shorter"] if months < 3 else d["longer"])
    pay = job.get("pay")
    if pay:   # small bonus for higher stated pay (not stated: no bonus, no penalty)
        pts += next((bonus for floor, bonus in sorted(c.get("pay_bonus") or [], reverse=True) if pay >= floor), 0)
    return int(pts)
