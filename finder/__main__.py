"""CLI: python -m finder {run,discover,verify,gaps}"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from . import discover as disc
from .classify import Classifier
from .pipeline import ROOT, configure_providers, load_companies, load_config, make_client, run

COMPANIES = ROOT / "companies.yaml"
GAPS = ROOT / "gaps.yaml"

HEADER = ("# Verified companies. Each entry was confirmed by a live response from its feed.\n"
          "# Add with: python -m finder discover \"<Company>\" <careers_url> --add\n")


def _save_companies(rows):
    rows = sorted(rows, key=lambda c: c["name"].lower())
    COMPANIES.write_text(HEADER + yaml.safe_dump({"companies": rows}, sort_keys=False, allow_unicode=True, width=200),
                         encoding="utf-8")


def _load_gaps():
    return (yaml.safe_load(GAPS.read_text(encoding="utf-8")) or {}).get("gaps", []) if GAPS.exists() else []


def _save_gaps(rows):
    rows = sorted(rows, key=lambda g: g["name"].lower())
    GAPS.write_text(yaml.safe_dump({"gaps": rows}, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8")


def _best(hits):
    good = [h for h in hits if h.get("jobs") and not h.get("error")]
    return max(good, key=lambda h: (h["focus"], h["jobs"])) if good else None


def cmd_discover(args):
    cfg = load_config()
    client, clf = make_client(cfg), Classifier(cfg)
    configure_providers(cfg, clf)
    if args.from_file:
        seeds = yaml.safe_load(Path(args.from_file).read_text(encoding="utf-8"))["seeds"]
    else:
        seeds = [{"name": args.name, "careers_url": args.careers_url, "sector": args.sector}]
    companies, gaps = load_companies(COMPANIES), _load_gaps()
    known = {c["name"].lower() for c in companies} | {g["name"].lower() for g in gaps}
    if args.from_file and not args.force:
        seeds = [s for s in seeds if s["name"].lower() not in known]
    with ThreadPoolExecutor(max_workers=8 if args.from_file else 1) as ex:
        results = ex.map(lambda s: (s, disc.discover(client, clf, s["name"], s.get("careers_url"),
                                                     do_probe=not args.no_probe,
                                                     extra_tokens=s.get("tokens", ()),
                                                     known_urls=s.get("urls", ()),
                                                     country=s.get("country", "CH"))), seeds)
        for s, r in results:
            best = _best(r["hits"])
            feed = lambda c: (c["provider"], c["token"], c.get("site"))  # noqa: E731
            dup = best and next((c["name"] for c in companies if c["name"].lower() != s["name"].lower()
                                 and feed(c) == (best["provider"], best["token"], best["opts"].get("site"))), None)
            if dup:
                print(f"{s['name'][:34]:<35} already tracked as '{dup}' ({best['provider']}:{best['token']}), "
                      f"{best['focus']} {s.get('country', 'CH')} postings")
                continue
            # In scope when the board has postings in any target country (the seed's country is its home market).
            if best and not best["by_country"] and not s.get("swiss_hq"):
                r["unsupported"] = r["unsupported"] or [f"{best['provider']} board has no postings in the target countries"]
                best = None
            if args.from_file:  # one compact line per company
                tag = (f"{best['provider']}:{best['token']} {best['jobs']} jobs/{best['focus']} {s.get('country', 'CH')}"
                       if best else "GAP " + (", ".join(r["unsupported"]) or "none found"))
                print(f"{s['name'][:34]:<35} {tag}")
            else:
                _print_detail(s, r)
            if not args.add:
                continue
            companies = [c for c in companies if c["name"].lower() != s["name"].lower()]
            old_gap = next((g for g in gaps if g["name"].lower() == s["name"].lower()), None)
            gaps = [g for g in gaps if g["name"].lower() != s["name"].lower()]
            if best:
                best["opts"] = {k: v for k, v in best["opts"].items() if not k.startswith("_")}
                companies.append({"name": s["name"], "provider": best["provider"], "token": best["token"],
                                  "country": s.get("country", "CH"),
                                  **best["opts"], "careers_url": s.get("careers_url"), "sector": s.get("sector"),
                                  "verified_at": disc.now_iso(), "jobs": best["jobs"],
                                  "jobs_by_country": best["by_country"], "evidence": best["evidence"]})
            else:
                blocked = [h for h in r["hits"] if "robots" in str(h.get("error"))]
                system = ", ".join(dict.fromkeys(r["unsupported"])) or (
                    f"{blocked[0]['provider']} (robots.txt disallows the feed)" if blocked else "unknown / not detected")
                gaps.append(merge_gap(old_gap, s, system, disc.now_iso()[:10]))
            _save_companies(companies)
            _save_gaps(gaps)


def merge_gap(old: dict | None, seed: dict, system: str, today: str) -> dict:
    """The gaps.yaml entry after a re-check. Keeps what an earlier check or a person wrote (priority, URL checks,
    a specific finding): a re-check that finds nothing new records itself under `recheck` instead of replacing a
    specific `system` text with "unknown / not detected"."""
    entry = {**(old or {}), "name": seed["name"], "careers_url": seed.get("careers_url") or (old or {}).get("careers_url"),
             "sector": seed.get("sector") or (old or {}).get("sector")}
    if seed.get("country", "CH") != "CH" or "country" in entry:
        entry["country"] = seed.get("country", entry.get("country", "CH"))
    if old and old.get("system") and system == "unknown / not detected" and old["system"] != system:
        entry["recheck"] = f"{today}: still no supported feed found"
    elif old and old.get("system") and len(old["system"]) > len(system) and all(
            part.strip().split()[0].lower() in old["system"].lower() for part in system.split(",") if part.strip()):
        entry["recheck"] = f"{today}: still {system}"     # same system; the older, more specific finding stays
    else:
        if old and old.get("system") and old["system"] != system:
            entry["recheck"] = f"{today}: was '{old['system']}'"
        else:
            entry.pop("recheck", None)
        entry["system"] = system
    entry["checked_at"] = today
    return entry


def _print_detail(s, r):
    print(f"== {s['name']}  ({s.get('careers_url')})")
    for h in r["hits"]:
        status = h.get("error") or f"{h.get('jobs')} jobs, by country {h.get('by_country')}"
        print(f"   {h['provider']}:{h['token']} {h['opts'] or ''} -> {status} [{h['evidence']}]"
              + (f" e.g. {h['samples'][:2]}" if h.get("samples") else ""))
    if not r["hits"]:
        print("   no supported ATS feed found")
    if r["unsupported"]:
        print(f"   unsupported systems referenced: {', '.join(r['unsupported'])}")
    for n in r["notes"]:
        print(f"   note: {n}")


def cmd_add_jsonld(args):
    """Add an employer served by the generic sitemap + JSON-LD provider, after a live check."""
    cfg = load_config()
    client, clf = make_client(cfg), Classifier(cfg)
    configure_providers(cfg, clf)
    opts = {"host": args.sitemap[0].split("/")[2], "sitemaps": args.sitemap}
    for k in ("sitemap_filter", "url_filter", "id_pattern", "prefer"):
        if getattr(args, k):
            opts[k] = getattr(args, k)
    if args.max_new:
        opts["max_new"] = args.max_new
    res = disc.check_feed(client, clf, args.name, args.provider, args.token, {**opts, "_verify_limit": args.sample})
    if res.get("error"):
        print(f"NOT ADDED: {res['error']}")
        return 1
    print(f"{args.name}: {res['jobs']} job URLs in sitemap; sampled {args.sample} pages -> "
          f"{res['parsed']} with job data; by target country (sample) {res['by_country']}")
    if not res["parsed"]:
        print("NOT ADDED: no job data (schema.org JobPosting) found on the sampled pages")
        return 1
    if not args.add:
        return 0
    companies = [c for c in load_companies(COMPANIES) if c["name"].lower() != args.name.lower()]
    companies.append({"name": args.name, "provider": args.provider, "token": args.token, "country": args.country, **opts,
                      "careers_url": args.careers_url, "sector": args.sector, "verified_at": disc.now_iso(),
                      "jobs": res["jobs"], "jobs_by_country": res["by_country"],
                      "evidence": f"sitemap + schema.org JobPosting ({args.provider}), verified live on {args.sample} sampled pages"})
    _save_companies(companies)
    _save_gaps([g for g in _load_gaps() if g["name"].lower() != args.name.lower()])
    print("ADDED")
    return 0


def cmd_health(args):
    from . import health
    return health.main(args)


def cmd_verify(args):
    cfg = load_config()
    client, clf = make_client(cfg), Classifier(cfg)
    configure_providers(cfg, clf)
    companies = load_companies(COMPANIES)
    todo = [c for c in companies if not args.only or args.only.lower() in c["name"].lower()]

    def check(c):
        opts = {k: c[k] for k in ("region", "domain", "host", "site", "extra_sites", "sitemaps", "sitemap_filter",
                                  "url_filter", "id_pattern", "prefer", "max_new", "section", "portal", "tenant", "sites",
                                  "keep_days") if k in c}
        if c["provider"] in ("jsonld", "successfactors", "phenom", "workday_sitemap"):
            opts["_verify_limit"] = 8   # light check: a few pages, cache untouched
        return c, disc.check_feed(client, clf, c["name"], c["provider"], c["token"], opts)

    bad, failures = 0, []
    with ThreadPoolExecutor(max_workers=cfg.get("http", {}).get("workers", 6)) as ex:
        for c, res in ex.map(check, todo):
            if "error" in res or res["jobs"] == 0:
                bad += 1
                c["last_verify_error"] = res.get("error", "feed returned 0 jobs")
                print(f"FAIL {c['name']:<32} {c['provider']}:{c['token']} -> {c['last_verify_error']}")
                failures.append(f"- **{c['name']}** ({c['provider']}:{c['token']}): {c['last_verify_error']}"
                                + (f" · careers page: {c['careers_url']}" if c.get("careers_url") else ""))
                continue
            c.pop("last_verify_error", None)
            c.pop("swiss_jobs", None)
            c.update(verified_at=disc.now_iso(), jobs=res["jobs"], jobs_by_country=res["by_country"])
            print(f"ok   {c['name']:<32} {c['provider']}:{c['token']} -> {res['jobs']} jobs, {res['by_country']}")
    if not args.no_save:
        _save_companies(companies)
    print(f"\n{len(todo) - bad} ok, {bad} failing")
    if args.report:
        Path(args.report).write_text(
            "" if not failures else
            f"The monthly feed check found **{bad} of {len(todo)} feeds not working** (an error, or 0 jobs):\n\n"
            + "\n".join(failures) + "\n\nA feed that fails for weeks has usually moved: see README *Troubleshooting*.\n",
            encoding="utf-8")
    return 1 if bad and args.strict else 0


def _check_url(client, url):
    """One polite GET. Returns (status label, final URL or None)."""
    from urllib.parse import urlsplit
    from .http import FetchError, RobotsDisallowed
    try:
        r = client.get(url)
    except RobotsDisallowed:
        return "not checked (robots.txt disallows)", None
    except FetchError as e:
        code = str(e).split()[1] if str(e).startswith("HTTP") else ""
        if code in ("401", "403", "429", "999"):
            return "site blocks automated requests: open in a browser", None
        if code in ("404", "410"):
            return f"HTTP {code}: URL may be outdated", None
        return "unreachable: " + str(e).split(" for ")[0][:60], None
    final = re.sub(r";jsessionid=[^?#]*", "", r.url, flags=re.I)  # drop session tokens
    if urlsplit(final).path in ("", "/") and urlsplit(url).path not in ("", "/"):
        return "redirects to homepage: check", final
    return "ok", final


_CAREER_LINK = re.compile(r'<a\b[^>]*href="([^"#]+)"[^>]*>(.*?)</a>', re.I | re.S)
_CAREER_WORD = re.compile(r"\b(careers?|jobs?|karriere|stellen(angebote)?|emplois?|carri[eè]res?|lavora|join us|work with us|arbeiten bei)\b", re.I)


def _repair_url(client, url):
    """Find the careers link on the company's own homepage. Returns a working URL or None."""
    from urllib.parse import urljoin, urlsplit
    parts = urlsplit(url)
    home = f"{parts.scheme}://{parts.netloc}/"
    try:
        page = client.get(home)
    except Exception:  # noqa: BLE001
        return None
    base_dom = ".".join(urlsplit(page.url).netloc.split(".")[-2:])
    for href, text in _CAREER_LINK.findall(page.text):
        label = re.sub(r"<[^>]+>", " ", text)
        cand = urljoin(page.url, href)
        if not (_CAREER_WORD.search(label) or _CAREER_WORD.search(urlsplit(cand).path.replace("-", " ").replace("/", " "))):
            continue
        if not urlsplit(cand).netloc.endswith(base_dom) or cand.rstrip("/") == page.url.rstrip("/"):
            continue
        status, final = _check_url(client, cand)
        if status == "ok":
            return final
    return None


COUNTRY_NAMES = {"CH": "Switzerland", "NL": "Netherlands", "LU": "Luxembourg", "AE": "United Arab Emirates", "BE": "Belgium",
                 "DE": "Germany", "UK": "United Kingdom", "AT": "Austria", "IE": "Ireland"}


def cmd_gaps(args):
    gaps = _load_gaps()
    if args.check_urls or args.recheck_urls:
        cfg = load_config()
        client = make_client(cfg)
        todo = [g for g in gaps if g.get("careers_url") and (args.recheck_urls or not g.get("url_checked_at"))]

        def check(g):
            status, final = _check_url(client, g["careers_url"])
            if status.startswith(("HTTP 404", "HTTP 410", "redirects to homepage")):
                fixed = _repair_url(client, g["careers_url"])
                if fixed:
                    status, final = "ok (found via homepage link)", fixed
            return g, status, final

        with ThreadPoolExecutor(max_workers=12) as ex:
            for g, status, final in ex.map(check, todo):
                g["url_status"] = status
                if status.startswith("ok") and final and final.rstrip("/") != g["careers_url"].rstrip("/"):
                    g["careers_url"] = final
                g["url_checked_at"] = disc.now_iso()[:10]
        _save_gaps(gaps)
        print(f"checked {len(todo)} careers URLs")

    def row(g, rank=None):
        url = g.get("careers_url") or ""
        cells = ([str(rank)] if rank else []) + [g["name"], g.get("sector") or "", f"[careers page]({url})" if url else "",
                                                 g["system"], g.get("url_status", "not checked")]
        return "| " + " | ".join(c.replace("|", "/") for c in cells) + " |"

    def table(rows):
        by = {}
        for g in rows:
            by.setdefault(g["system"], []).append(g)
        out = []
        for system in sorted(by, key=lambda s: (-len(by[s]), s)):
            out += [f"#### {system} ({len(by[system])})", "", "| Company | Sector | Careers page | System | URL check |",
                    "|---|---|---|---|---|"]
            out += [row(g) for g in sorted(by[system], key=lambda g: g["name"].lower())]
            out.append("")
        return out

    country = lambda g: g.get("country", "CH")  # noqa: E731
    top = sorted((g for g in gaps if g.get("priority")), key=lambda g: g["priority"])
    out = ["# Coverage gaps", "",
           f"{len(gaps)} in-scope employers whose postings this tool cannot read: they use a system without a "
           "supported public feed, their careers site could not be analysed automatically (JavaScript-only, blocked "
           "for bots, or robots.txt), or their feed currently has no postings in that country.",
           "", "Generated from `gaps.yaml` by `python -m finder gaps`. The *URL check* column is the result of one "
           "automated request; \"blocks automated requests\" usually still works in a browser.", "",
           "## Switzerland: top 30 to check by hand", "",
           "Employers most likely to hire business interns (marketing, sales, strategy, finance, communications).", "",
           "| # | Company | Sector | Careers page | System | URL check |", "|---|---|---|---|---|---|"]
    out += [row(g, g["priority"]) for g in top]
    for code in sorted({country(g) for g in gaps}, key=lambda c: (c != "CH", c)):
        rows = [g for g in gaps if country(g) == code and not g.get("priority")]
        if rows:
            out += ["", f"## {COUNTRY_NAMES.get(code, code)}: {'other gaps' if code == 'CH' else 'gaps'} by system "
                        f"({len(rows)})", ""] + table(rows)
    (ROOT / "gaps.md").write_text("\n".join(out), encoding="utf-8")
    print(f"gaps.md: {len(gaps)} companies ({len(top)} prioritised)")


def cmd_build(_args):
    from . import store
    from .pipeline import build_viewer
    info = build_viewer(load_config(), store.load(ROOT / "data" / "jobs.json"))
    print(f"docs/index.html rebuilt: {info['jobs']} postings embedded, "
          f"{info['removed_by_user_state']} removed via data/user_state.json, "
          f"{info['descriptions']} descriptions, {info['bytes'] / 1e6:.1f} MB")


def cmd_run(args):
    s = run(only=args.only)
    print(f"companies {s['companies_ok']}/{s['companies']} ok | postings fetched {s['postings_fetched']} | "
          f"postings by country {s['postings_by_country']} | internship matches {s['matched']} | new {s['new']} | location unclear {s['location_unclear']}"
          f" | descriptions {s['descriptions']}")
    for f in s["failed"]:
        print(f"  failed: {f['company']} ({f['provider']}): {f['error'][:120]}")
    return 0


def main(argv=None):
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="finder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="fetch all feeds and update data/ and docs/")
    p.add_argument("--only", help="substring of company name")
    p = sub.add_parser("discover", help="detect the ATS behind a careers page")
    p.add_argument("name", nargs="?")
    p.add_argument("careers_url", nargs="?")
    p.add_argument("--sector")
    p.add_argument("--add", action="store_true", help="write result to companies.yaml / gaps.yaml")
    p.add_argument("--from-file", help="YAML file with seeds: [{name, careers_url, sector}]")
    p.add_argument("--force", action="store_true", help="re-check companies already known")
    p.add_argument("--no-probe", action="store_true", help="do not guess tokens from the name")
    p = sub.add_parser("add-jsonld", help="add an employer via sitemap + schema.org JobPosting (live-checked)")
    p.add_argument("--provider", default="jsonld", choices=["jsonld", "successfactors"],
                   help="jsonld (JSON-LD on job pages) or successfactors (SAP SuccessFactors RMK microdata)")
    p.add_argument("name")
    p.add_argument("token")
    p.add_argument("sitemap", nargs="+", help="sitemap or sitemap-index URL(s)")
    p.add_argument("--sitemap-filter", dest="sitemap_filter")
    p.add_argument("--url-filter", dest="url_filter")
    p.add_argument("--id-pattern", dest="id_pattern")
    p.add_argument("--prefer")
    p.add_argument("--max-new", dest="max_new", type=int)
    p.add_argument("--careers-url", dest="careers_url")
    p.add_argument("--sector")
    p.add_argument("--sample", type=int, default=12, help="job pages to check before adding")
    p.add_argument("--country", default="CH", help="home country of the employer (informational)")
    p.add_argument("--add", action="store_true")
    p = sub.add_parser("verify", help="confirm each feed in companies.yaml still returns jobs")
    p.add_argument("--only")
    p.add_argument("--strict", action="store_true", help="exit 1 if any feed fails")
    p.add_argument("--report", help="write a Markdown list of failing feeds here (empty file if none)")
    p.add_argument("--no-save", dest="no_save", action="store_true", help="don't update companies.yaml")
    p = sub.add_parser("health", help="check a run summary (used by the daily workflow)")
    p.add_argument("--previous", help="the previous run's last_run.json")
    p.add_argument("--current", default="data/last_run.json")
    p.add_argument("--outcome", help="workflow step outcomes, e.g. tests=success,run=failure")
    p.add_argument("--run-url", dest="run_url")
    p.add_argument("--out", help="write the Markdown report here")
    p = sub.add_parser("gaps", help="render gaps.md from gaps.yaml")
    p.add_argument("--check-urls", action="store_true", help="check careers URLs not checked yet (polite, robots-aware)")
    p.add_argument("--recheck-urls", action="store_true", help="re-check every careers URL")
    sub.add_parser("build", help="rebuild docs/index.html from data/jobs.json (no fetching)")
    args = ap.parse_args(argv)
    if args.cmd == "discover" and not (args.from_file or args.name):
        ap.error("discover needs <name> [careers_url] or --from-file")
    return {"run": cmd_run, "discover": cmd_discover, "verify": cmd_verify, "gaps": cmd_gaps, "health": cmd_health, "build": cmd_build, "add-jsonld": cmd_add_jsonld}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
