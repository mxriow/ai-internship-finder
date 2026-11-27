"""Build docs/index.html: a single self-contained page with the jobs data embedded.

If data/user_state.json exists (the viewer's Export, pasted into the repo), it is applied
at build time: hidden jobs and hidden companies are left out, starred/applied are marked.
"""
from __future__ import annotations

import base64
import gzip
import json
import logging
from datetime import date, timedelta
from pathlib import Path

from . import fit

log = logging.getLogger(__name__)

TEMPLATE = Path(__file__).with_name("viewer_template.html")
KEEP = ("title", "company", "locations", "cities", "countries", "category", "needs_review", "review_reason",
        "language", "type", "duration", "start", "start_month", "start_asap", "stale", "pay", "pay_max", "pay_compulsory",
        "pay_text", "pay_basis", "compulsory_only", "posted", "department", "url", "first_seen", "last_seen", "status",
        "degree", "degree_note", "lang_required", "lang_plus", "deadline", "deadline_text", "closed_on")
MAX_BYTES = 12_000_000   # keep docs/index.html below this; closed postings' descriptions are dropped first

CATEGORY_LABELS = {
    "marketing": "Marketing", "brand": "Brand", "sales": "Sales", "business_development": "Business development",
    "strategy": "Strategy", "consulting": "Consulting", "ecommerce_digital": "E-commerce / digital",
    "commercial": "Commercial", "marketing_analytics": "Marketing analytics / insights",
    "communications_pr": "Communications / PR", "operations_supply_chain": "Operations / supply chain",
    "finance": "Finance", "hr": "HR", "other_business": "Other business", "excluded": "Technical / excluded",
}


def load_user_state(path: Path) -> dict:
    """Read the exported viewer state. Anything malformed is ignored (never breaks a run)."""
    empty = {"hidden": set(), "hidden_companies": set(), "starred": set(), "applied": set()}
    if not path.exists():
        return empty
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
        return {k: {str(x) for x in raw.get(k, []) if isinstance(x, (str, int))} for k in empty}
    except (ValueError, AttributeError, TypeError) as e:
        log.warning("ignoring malformed %s: %s", path, e)
        return empty


def pack_descriptions(texts: dict[str, str]) -> list[str]:
    """{posting id: text} -> base64 gzip chunks, one per feed (provider:token).

    One chunk per feed keeps each chunk stable while that feed's postings don't change (smaller git deltas)
    and lets similar texts of one employer compress together. gzip with mtime=0, so a rebuild with the same
    data gives the same bytes. The page decodes them with DecompressionStream("gzip")."""
    feeds: dict[str, dict[str, str]] = {}
    for jid in sorted(texts):
        feeds.setdefault(":".join(jid.split(":", 2)[:2]), {})[jid] = texts[jid]
    out = []
    for feed in sorted(feeds):
        raw = json.dumps(feeds[feed], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        out.append(base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode("ascii"))
    return out


def embeddable(job: dict, today: str, closed_days: int) -> bool:
    """Open postings, and postings closed in the last `closed_days` days."""
    if job.get("status") == "open":
        return True
    since = (date.fromisoformat(today) - timedelta(days=closed_days)).isoformat()
    return (job.get("closed_on") or job.get("last_seen") or "") >= since


def build(db: dict, out: Path, user_state: Path | None = None, default_categories: list[str] | None = None,
          countries: list[str] | None = None, early_before: str | None = None, fit_cfg: dict | None = None,
          archive=None, country_names: dict | None = None, embed_closed_days: int = 30,
          max_bytes: int = MAX_BYTES) -> dict:
    state = load_user_state(user_state) if user_state else load_user_state(Path("/nonexistent"))
    jobs, removed = {}, 0
    for jid, j in db["jobs"].items():
        if jid in state["hidden"] or j.get("company") in state["hidden_companies"]:
            removed += 1
            continue
        rec = {k: j.get(k) for k in KEEP}
        rec["fit"] = fit.score(j, fit_cfg, early_before)
        rec["starred"] = jid in state["starred"]
        rec["applied"] = jid in state["applied"]
        jobs[jid] = rec
    page = {
        "generated_at": db.get("generated_at"),
        "jobs": jobs,
        "config": {
            "default_categories": default_categories or [],
            "category_labels": CATEGORY_LABELS,
            "countries": countries or [],
            "early_before": early_before or "",
            "build_hidden": removed,
            "country_names": country_names or {},
        },
    }
    payload = json.dumps(page, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")  # never let data close the <script> element
    out.parent.mkdir(parents=True, exist_ok=True)
    html = TEMPLATE.read_text(encoding="utf-8").replace("__COUNTRIES__", " ".join(countries or []))
    html = html.replace("__JOBS_JSON__", payload)

    today = (db.get("generated_at") or date.today().isoformat())[:10]
    texts = {}
    if archive is not None:
        texts = archive.all_for(jid for jid, j in db["jobs"].items() if jid in jobs and embeddable(j, today, embed_closed_days))
    final = html.replace("__DESC_JSON__", json.dumps(pack_descriptions(texts)))
    if len(final.encode("utf-8")) > max_bytes:      # too big: keep only open postings' descriptions
        texts = {jid: t for jid, t in texts.items() if db["jobs"][jid].get("status") == "open"}
        final = html.replace("__DESC_JSON__", json.dumps(pack_descriptions(texts)))
        log.warning("viewer over %d bytes: embedded descriptions of open postings only", max_bytes)
    out.write_text(final, encoding="utf-8")
    return {"jobs": len(jobs), "removed_by_user_state": removed, "descriptions": len(texts),
            "bytes": len(final.encode("utf-8"))}
