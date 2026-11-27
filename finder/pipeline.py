"""Daily run: fetch every company feed, classify, merge, write outputs."""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import descriptions, report, store, viewer
from .classify import Classifier
from .http import PoliteClient
from .providers import PROVIDERS, _common, jsonld, successfactors, workday

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
VAGUE_LOCATION = re.compile(r"^\s*$|europe|emea|dach|multiple|various|flexible|hybrid|anywhere|global|worldwide", re.I)


def load_config(path: Path = ROOT / "config.yaml") -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_companies(path: Path = ROOT / "companies.yaml") -> list[dict]:
    if not path.exists():
        return []
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("companies", [])


def configure_providers(cfg: dict, clf: Classifier) -> None:
    targets = {code: [cfg["countries"][code]["name"], *cfg["countries"][code].get("names", [])]
               for code in cfg["target_countries"]}
    workday.configure(targets, detail_filter=lambda title: clf.intern_type(title) is not None)
    _common.configure(country_targets=targets,
                      codes=[x for code in cfg["target_countries"] for x in cfg["countries"][code].get("codes", [])],
                      details=lambda title, employment=None: clf.intern_type(title, employment) is not None)
    jsonld.configure(cache_dir=ROOT / "data" / "cache" / "jsonld",
                     detail_filter=lambda title, employment: clf.intern_type(title, employment) is not None,
                     url_in_scope=lambda text: bool(clf.location([text])[0]),
                     url_priority=lambda text: clf.intern_type(text) is not None)
    successfactors.configure(slug_in_scope=lambda text: bool(clf.location([text])[0]),
                             slug_priority=lambda text: clf.intern_type(text) is not None,
                             detail_filter=lambda title, employment: clf.intern_type(title, employment) is not None)


def build_viewer(cfg: dict, db: dict, out: Path = ROOT / "docs" / "index.html",
                 user_state: Path = ROOT / "data" / "user_state.json", archive=None) -> dict:
    if archive is None:
        archive = descriptions.Archive(ROOT / "data" / "descriptions")
    return viewer.build(db, out, user_state=user_state, default_categories=cfg.get("default_view_categories"),
                        countries=cfg.get("target_countries"), early_before=cfg.get("early_start_before"),
                        fit_cfg=cfg.get("fit_score"), archive=archive,
                        country_names={c: cfg["countries"][c]["name"] for c in cfg.get("target_countries", [])},
                        embed_closed_days=(cfg.get("viewer") or {}).get("embed_closed_days", 30))


def make_client(cfg: dict) -> PoliteClient:
    h = cfg.get("http", {})
    return PoliteClient(cfg["user_agent"], h.get("max_rps_per_host", 2), h.get("timeout", 30), h.get("retries", 2))


def company_key(c: dict) -> str:
    return f"{c['provider']}:{c['token']}"


def retire_replaced(companies: list[dict], ok: set[str]) -> set[str]:
    """A feed that `replaces` an older one (e.g. a company's own job site standing in for a blocked Workday
    feed) lets the old feed's postings age out: once the new feed has worked, the old key counts as fetched,
    so its stored postings close after the usual missed runs instead of staying open forever."""
    for c in companies:
        if c.get("replaces") and company_key(c) in ok:
            ok.add(c["replaces"])
    return ok


def fetch_all(client, companies, workers=6):
    """Fetch every company; failures are logged and returned, never raised."""
    def one(c):
        try:
            return c, PROVIDERS[c["provider"]].fetch(client, c), None
        except Exception as e:  # noqa: BLE001 - one bad feed must not stop the run
            log.warning("FAILED %s (%s:%s): %s", c["name"], c["provider"], c["token"], e)
            return c, [], f"{type(e).__name__}: {e}"
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, companies))


def to_record(p, res) -> dict:
    return {
        "id": p.id, "title": p.title, "company": p.company, "provider": p.provider,
        "locations": p.locations, "cities": res.cities, "countries": res.countries,
        "category": res.category, "needs_review": res.needs_review, "review_reason": res.review_reason,
        "language": res.language, "type": res.intern_type, "employment": p.employment_raw,
        "duration": res.duration, "start": res.start, "start_month": res.start_month, "start_asap": res.start_asap,
        "stale": res.stale, "posted": p.posted,
        "pay": res.pay, "pay_max": res.pay_max, "pay_compulsory": res.pay_compulsory, "pay_text": res.pay_text,
        "pay_basis": res.pay_basis, "compulsory_only": res.compulsory_only,
        "degree": res.degree, "degree_note": res.degree_note,
        "lang_required": res.lang_required, "lang_plus": res.lang_plus,
        "deadline": res.deadline, "deadline_text": res.deadline_text,
        "department": p.department, "url": p.url, "apply_url": p.apply_url,
    }


def run(data_dir: Path = ROOT / "data", docs_dir: Path = ROOT / "docs", only: str | None = None) -> dict:
    cfg = load_config()
    clf = Classifier(cfg)
    configure_providers(cfg, clf)
    companies = [c for c in load_companies() if not c.get("disabled")]
    if only:
        companies = [c for c in companies if only.lower() in c["name"].lower()]
    client = make_client(cfg)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    today = now[:10]

    results = fetch_all(client, companies, cfg.get("http", {}).get("workers", 6))
    records, unclear, stats, ok = [], [], [], set()
    texts = {}                          # posting id -> description, for the archive
    total = 0
    for c, postings, err in results:
        st = {"company": c["name"], "provider": c["provider"], "fetched": len(postings), "matched": 0, "error": err}
        if err is None:
            ok.add(company_key(c))
        for p in postings:
            total += 1
            for code in clf.location(p.locations, p.country_codes)[0]:
                st.setdefault("by_country", {})
                st["by_country"][code] = st["by_country"].get(code, 0) + 1
            res = clf.classify(p)
            if not res.intern_type:
                continue
            if res.countries:
                records.append(to_record(p, res))
                if p.description:
                    texts[p.id] = p.description
                st["matched"] += 1
            elif not p.locations or all(VAGUE_LOCATION.search(l) for l in p.locations):
                unclear.append({"company": p.company, "title": p.title, "url": p.url, "locations": p.locations})
        stats.append(st)

    retire_replaced(companies, ok)
    db_path = data_dir / "jobs.json"
    db = store.load(db_path)
    records, dup_ids = store.dedupe(records)
    for jid in dup_ids:                 # a duplicate stored by an earlier run is removed, not closed
        db["jobs"].pop(jid, None)
    new_ids = store.merge(db, records, ok, today, now)
    store.save(db_path, db)
    archive = descriptions.Archive(data_dir / "descriptions")
    desc_new = desc_updated = 0
    for rec in records:                 # a duplicate's text stands in when the kept posting has none
        text = texts.get(rec["id"]) or next((texts[d] for d in rec.get("duplicates", []) if texts.get(d)), "")
        change = archive.update(rec["id"], text, today)
        desc_new += change == "new"
        desc_updated += change == "updated"
    for jid in dup_ids:
        archive.remove(jid)
    archive.save()
    report.write_new_today(data_dir / "new_today.md", db, new_ids, now)
    report.write_review(data_dir / "review.md", db, unclear, now)
    page = build_viewer(cfg, db, docs_dir / "index.html", data_dir / "user_state.json", archive)

    summary = {
        "run_at": now, "companies": len(companies), "companies_ok": sum(1 for s in stats if not s["error"]),
        "postings_fetched": total, "postings_by_country": {code: sum(s.get("by_country", {}).get(code, 0) for s in stats)
                                for code in cfg["target_countries"]},
        "matched": len(records), "duplicates_removed": len(dup_ids), "new": len(new_ids),
        "location_unclear": len(unclear),
        "descriptions": {"matched_with_text": sum(1 for r in records if archive.get(r["id"])),
                         "new": desc_new, "updated": desc_updated, "embedded_in_viewer": page.get("descriptions", 0)},
        "viewer_bytes": page.get("bytes"),
        "failed": [s for s in stats if s["error"]],
        "per_company": sorted(stats, key=lambda s: -s["matched"]),
    }
    (data_dir / "last_run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return summary
