"""Detect which ATS a careers page uses, and verify company feeds."""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from .classify import Classifier
from .http import RobotsDisallowed
from .providers import PROVIDERS, eightfold, greenhouse

log = logging.getLogger(__name__)

# provider -> regex with one group for the token (and an optional variant group)
SUPPORTED = {
    "greenhouse": re.compile(r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([A-Za-z0-9_-]+)"),
    "greenhouse_embed": re.compile(r"greenhouse\.io/embed/job_board(?:/js)?\?for=([A-Za-z0-9_-]+)"),
    "lever": re.compile(r"jobs\.(eu\.)?lever\.co/([A-Za-z0-9_.-]+)"),
    "ashby": re.compile(r"(?:jobs\.ashbyhq\.com/|organizationHostedJobsPageName=)([A-Za-z0-9_.%-]+)"),
    "smartrecruiters": re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9_-]+)"),
    "recruitee": re.compile(r"(?<![a-z0-9-])([a-z0-9-]{1,63})\.recruitee\.com"),
    "personio": re.compile(r"(?<![a-z0-9-])([a-z0-9-]{1,63})\.jobs\.personio\.(de|com)"),
    # tenant.wdN.myworkdayjobs.com/[xx-XX/]Site  or  wdN.myworkdaysite.com/[xx-XX/]recruiting/tenant/Site
    "workday": re.compile(r"(?:(?<![a-z0-9-])([a-z0-9-]{1,63})\.(wd\d+)\.myworkdayjobs\.com|(wd\d+)\.myworkdaysite\.com/(?:[a-z]{2}-[A-Z]{2}/)?recruiting/([a-z0-9-]+))"
                          r"/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)"),
}
SUPPORTED.update({
    "eightfold": re.compile(r"https?://([a-z0-9-]+)\.eightfold\.ai"),
    "oracle": re.compile(r"(?<![a-z0-9-])([a-z0-9-]{1,63})\.(fa\.[a-z0-9-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/[a-z]{2}(?:-[A-Z]{2})?/sites/([A-Za-z0-9_]+)"),
    "taleo": re.compile(r"(?<![a-z0-9-])([a-z0-9-]{1,63})\.taleo\.net/careersection/([a-z0-9_]+)/"),
    "teamtailor": re.compile(r"(?<![a-z0-9-])([a-z0-9-]{1,63})\.teamtailor\.com"),
    "bamboohr": re.compile(r"(?<![a-z0-9-])([a-z0-9-]{1,63})\.bamboohr\.com"),
    "join": re.compile(r"join\.com/companies/([A-Za-z0-9_-]{2,80})"),
    "hibob": re.compile(r"(?<![a-z0-9-])([a-z0-9-]{1,63})\.careers\.hibob\.com"),
    "umantis": re.compile(r"(?<![a-z0-9-])(recruitingapp-\d{1,7})((?:\.[a-z]{2})?\.umantis\.com)"),
})
# Job systems whose own hosts publish a sitemap of job pages with schema.org JobPosting: read with the generic
# `jsonld` provider (sitemap + JSON-LD). host regex -> settings; "{host}" is filled in. `robots: True` takes the
# sitemaps the host's robots.txt lists (Avature lists one per public portal and disallows everything else).
SITEMAP_ATS = {
    "softgarden": (re.compile(r"(?<![a-z0-9-])([a-z0-9-]{1,63}\.softgarden\.io)"),
                   {"sitemaps": ["https://{host}/sitemap.xml"], "url_filter": r"/job/\d+", "id_pattern": r"/job/(\d+)"}),
    "avature": (re.compile(r"(?<![a-z0-9-])([a-z0-9-]{1,63}\.avature\.net)"), {"robots": True}),
}
SITEMAP_ATS_IGNORE = {"www", "cdn", "static", "assets", "app", "api", "career", "matomo", "pcw-api", "pcw-cdn"}
# Career-site platforms recognised by markers in the page itself (the page's own host serves the jobs).
PAGE_MARKERS = {
    "phenom": re.compile(r"phenompeople\.com|cdn\.phenom|\"phApp\"|phenom-", re.I),
    # Teamtailor career sites on the employer's own domain (careers.axpo.com): the RSS feed is on that host.
    "teamtailor": re.compile(r"teamtailor-cdn\.com|assets\.teamtailor-cdn|<meta[^>]+content=\"Teamtailor\"", re.I),
    "successfactors": re.compile(r"rmkcdn\.successfactors\.com|/platform/css/j2w/|/platform/js/j2w/", re.I),
}
SITEMAP_PROVIDERS = {"jsonld", "successfactors", "phenom", "workday_sitemap"}   # verified on a sample of pages, not a full crawl
VERIFY_SAMPLE = 12
WORKDAY_NOT_SITES = {"wday", "job", "jobs", "login", "apply", "refreshfacet", "en", "de", "fr"}
IGNORE_TOKENS = {"embed", "api", "www", "jobs", "careers", "static", "assets", "cdn", "app", "v1"}

UNSUPPORTED = {      # name shown in gaps.yaml -> marker; the name says why the system is not read
    "SuccessFactors": re.compile(r"successfactors\.(com|eu)|sapsf\.(com|eu)|jobs\.sap\.com|career\d*\.sap"),
    "Oracle Cloud / Taleo": re.compile(r"taleo\.net|oraclecloud\.com"),
    "iCIMS (robots.txt disallows all bots)": re.compile(r"icims\.com"),
    "Workable (job API answers HTTP 429 with a 13-hour Retry-After to automated requests)": re.compile(r"apply\.workable\.com|workable\.com/"),
    "Avature (only portals listed in robots.txt are allowed)": re.compile(r"avature\.net"),
    "Phenom": re.compile(r"phenompeople\.com|phenom\.com"),
    "Eightfold": re.compile(r"eightfold\.ai"),
    "Jobvite": re.compile(r"jobvite\.com"),
    "Pinpoint (robots.txt disallows the job feed)": re.compile(r"pinpointhq\.com"),
    "rexx": re.compile(r"rexx-systems\.com"),
    "d.vinci": re.compile(r"dvinci(-hr)?\.(com|de)|dvinci-easy"),
    "Cornerstone (job API needs a session token; no public feed)": re.compile(r"csod\.com"),
    "Beamery": re.compile(r"beamery\.com"),
    "onlyfy (no feed or structured job data)": re.compile(r"onlyfy\.jobs|prescreenapp\.io"),
    "Radancy / TalentBrew (no public feed)": re.compile(r"tbcdn\.talentbrew|radancy", re.I),
    "SmartRecruiters (robots.txt disallows API)": re.compile(r"(?:careers|jobs)\.smartrecruiters\.com"),
}

LEGAL = re.compile(r"\b(ag|sa|s\.a\.|gmbh|ltd|limited|inc|plc|llc|holding|holdings|group|groupe|gruppe|"
                   r"switzerland|schweiz|suisse|international|company|co|corp|corporation|se|nv|bv)\b\.?", re.I)


def slug_candidates(name: str) -> list[str]:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    n = n.replace("&", " and ")
    core = re.sub(r"\s+", " ", LEGAL.sub(" ", re.sub(r"[^a-z0-9& ]", " ", n))).strip()
    full = re.sub(r"[^a-z0-9 ]", " ", n).split()
    out = []
    for words in (core.split(), full):
        if words:
            out += ["".join(words), "-".join(words)]
    return list(dict.fromkeys(s for s in out if len(s) >= 2))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower())


def _core(s: str) -> str:
    """Normalised name without legal suffixes: 'Proton AG' -> 'proton'."""
    return _norm(LEGAL.sub(" ", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()))


def scan_html(html: str) -> tuple[list[tuple[str, str, dict]], list[str]]:
    """Return ([(provider, token, opts)], [unsupported system names]) found in a page."""
    found = []
    for prov, rx in SUPPORTED.items():
        for m in rx.finditer(html):
            opts = {}
            if prov == "lever":
                opts = {"region": "eu"} if m.group(1) else {}
                token = m.group(2)
            elif prov == "workday":
                if m.group(1):
                    token, host = m.group(1), f"{m.group(1)}.{m.group(2)}.myworkdayjobs.com"
                else:
                    token, host = m.group(4), f"{m.group(3)}.myworkdaysite.com"
                if m.group(5).lower() in WORKDAY_NOT_SITES:
                    continue
                opts = {"host": host, "site": m.group(5)}
            elif prov == "personio":
                token, opts = m.group(1), ({"domain": "com"} if m.group(2) == "com" else {})
            elif prov == "oracle":
                token, opts = m.group(1), {"host": f"{m.group(1)}.{m.group(2)}", "site": m.group(3)}
            elif prov == "taleo":
                token, opts = m.group(1), {"host": f"{m.group(1)}.taleo.net", "section": m.group(2)}
            elif prov == "eightfold" and m.group(1) in ("app", "www", "static", "cdn"):
                continue
            elif prov == "teamtailor":
                if m.group(1).lower() in SITEMAP_ATS_IGNORE | {"career", "support", "docs", "partner"}:
                    continue
                token, opts = m.group(1), {"host": f"{m.group(1)}.teamtailor.com"}
            elif prov == "bamboohr" and m.group(1).lower() in SITEMAP_ATS_IGNORE:
                continue
            elif prov == "umantis":
                token, opts = m.group(1), {"host": m.group(1) + m.group(2)}
            else:
                token = m.group(1)
            token = token.rstrip(".")
            if token.lower() in IGNORE_TOKENS:
                continue
            p = "greenhouse" if prov == "greenhouse_embed" else prov
            if (p, token, opts) not in found:
                found.append((p, token, opts))
    for system, (rx, settings) in SITEMAP_ATS.items():
        for m in rx.finditer(html):
            host = m.group(1).lower()
            if host.split(".")[0] in SITEMAP_ATS_IGNORE:
                continue
            opts = {"host": host, **{k: ([u.format(host=host) for u in v] if isinstance(v, list) else v)
                                     for k, v in settings.items()}}
            hit = ("jsonld", f"{re.sub(r'[^a-z0-9]+', '-', host.split('.')[0])}-{system[:2]}", opts)
            if hit not in found:
                found.append(hit)
    other = [name for name, rx in UNSUPPORTED.items() if rx.search(html)]
    return found, other


_JOBLINK = re.compile(r'href="([^"#]+)"[^>]*>', re.I)
_JOBWORD = re.compile(r"job|career|karriere|stellen|emploi|offres|vacanc|opening|lavora|jobs", re.I)


def _marker_hits(html, url):
    host = urlsplit(url).netloc
    slug = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")
    hits = []
    for prov, rx in PAGE_MARKERS.items():
        if host and rx.search(html):
            opts = {"host": host}
            if prov == "successfactors":
                opts["sitemaps"] = [f"https://{host}/sitemap.xml"]
            if prov == "teamtailor" and host.endswith(".teamtailor.com"):
                continue                       # found by the link pattern already
            hits.append((prov, f"{slug}-{prov[:2]}", opts))
    return hits


def fetch_page_scan(client, url):
    """Scan the careers page plus up to 3 same-site job-looking links."""
    notes, found, other = [], [], []
    try:
        r = client.get(url)
    except RobotsDisallowed:
        return [], [], ["careers page disallowed by robots.txt; not fetched"]
    except Exception as e:  # noqa: BLE001
        return [], [], [f"careers page not fetched: {e}"]
    html = r.text
    f, o = scan_html(html + " " + r.url)
    found += f
    other += o
    found += [x for x in _marker_hits(html, r.url) if x not in found]
    if not found:
        host = urlsplit(r.url).netloc
        links = []
        for m in _JOBLINK.finditer(html):
            u = urljoin(r.url, m.group(1))
            if _JOBWORD.search(urlsplit(u).path + urlsplit(u).netloc) and u != r.url and u not in links:
                if urlsplit(u).netloc == host or any(x.search(u) for x in SUPPORTED.values()):
                    links.append(u)
        for u in links[:3]:
            f2, o2 = scan_html(u)
            if not f2:
                try:
                    r2 = client.get(u)
                    f2, o2 = scan_html(r2.text + " " + r2.url)
                    f2 += _marker_hits(r2.text, r2.url)
                except Exception as e:  # noqa: BLE001
                    notes.append(f"sub-page {u} not fetched: {e}")
            found += [x for x in f2 if x not in found]
            other += [x for x in o2 if x not in other]
    return found, other, notes


def check_feed(client, clf: Classifier, name, provider, token, opts, country=None):
    """Fetch a feed; return job counts (total, per target country, and `focus`: postings in
    `country`, or in any target country when None), or {"error": ...}."""
    company = {"name": name, "provider": provider, "token": token, **opts}
    try:
        postings = PROVIDERS[provider].fetch(client, company)
    except RobotsDisallowed as e:
        return {"error": f"robots.txt disallows ({e})"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:120]}
    by_country, focus = {}, []
    for p in postings:
        codes = clf.location(p.locations, p.country_codes)[0]
        for code in codes:
            by_country[code] = by_country.get(code, 0) + 1
        if (country in codes) if country else codes:
            focus.append(p)
    return {"jobs": getattr(postings, "total", len(postings)), "parsed": len(postings),
            "by_country": by_country, "focus": len(focus),
            "samples": [p.title for p in focus[:3]] or [p.title for p in postings[:3]]}


def probe(client, clf, name, extra_tokens=(), country=None):
    """Guess tokens from the company name. Only returns hits with supporting evidence."""
    hits = []
    for slug in list(dict.fromkeys(list(extra_tokens) + slug_candidates(name))):
        for provider, opts in (("greenhouse", {}), ("lever", {}), ("lever", {"region": "eu"}),
                               ("ashby", {}), ("recruitee", {}), ("personio", {}), ("personio", {"domain": "com"})):
            if any(h["provider"] == provider for h in hits):
                continue
            res = check_feed(client, clf, name, provider, slug, opts, country)
            if not res or "error" in res or res["jobs"] == 0:
                continue
            evidence = []
            if provider == "greenhouse":
                bn = greenhouse.board_name(client, slug) or ""
                if _core(bn) and _core(bn) == _core(name):
                    evidence.append(f"board name '{bn}'")
            if res["focus"]:
                evidence.append(f"{res['focus']} postings in {country or 'target countries'}")
            if evidence:
                hits.append({"provider": provider, "token": slug, "opts": opts, **res,
                             "evidence": "slug probe: " + ", ".join(evidence)})
    return hits


def workday_sites(client, host):
    """Public career sites a Workday tenant lists in its own robots.txt."""
    try:
        r = client.get(f"https://{host}/robots.txt", ok_404=True)
        txt = r.text if r is not None else ""
    except Exception:  # noqa: BLE001
        return []
    sites = re.findall(r"(?im)^\s*(?:allow:\s*/|sitemap:\s*https?://[^/]+/)([A-Za-z0-9_-]+)/", txt)
    return [x for x in dict.fromkeys(sites) if x.lower() not in WORKDAY_NOT_SITES and "internal" not in x.lower()]


def _check_workday(client, clf, name, token, opts, country=None):
    """Try the given site; if it fails, try the sites listed in the tenant's robots.txt."""
    res = check_feed(client, clf, name, "workday", token, opts, country)
    if not res.get("error"):
        return opts, res
    best = (opts, res)
    for site in workday_sites(client, opts["host"]):
        if site == opts["site"]:
            continue
        o = {**opts, "site": site}
        r = check_feed(client, clf, name, "workday", token, o, country)
        if not r.get("error") and (best[1].get("error") or (r["focus"], r["jobs"]) > (best[1]["focus"], best[1]["jobs"])):
            best = (o, r)
    return best


def _check(client, clf, name, provider, token, opts, country):
    """Verify one detected feed live. Returns (opts, result); opts may be completed (Workday site, Eightfold host)."""
    if provider == "eightfold" and "domain" not in opts:
        try:
            opts = {**opts, **eightfold.resolve(client, token)}
        except Exception as e:  # noqa: BLE001
            return opts, {"error": str(e)[:120]}
    if provider == "workday":
        return _check_workday(client, clf, name, token, opts, country)
    if provider == "jsonld" and opts.pop("robots", False):
        opts = {**opts, "sitemaps": robots_sitemaps(client, opts["host"])}
        if not opts["sitemaps"]:
            return opts, {"error": "robots.txt lists no sitemaps"}
    if provider in SITEMAP_PROVIDERS:
        res = check_feed(client, clf, name, provider, token, {**opts, "_verify_limit": VERIFY_SAMPLE}, country)
        if not res.get("error") and not res.get("parsed"):
            res["error"] = "no job data (schema.org JobPosting) on the sampled pages"
        return opts, res
    return opts, check_feed(client, clf, name, provider, token, opts, country)


def robots_sitemaps(client, host, limit=3):
    """Sitemaps a host's robots.txt lists (only those robots.txt itself allows us to fetch)."""
    try:
        txt = client.get(f"https://{host}/robots.txt", ok_404=True)
    except Exception:  # noqa: BLE001
        return []
    found = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", txt.text if txt is not None else "")
    return [u for u in found if client.allowed(u)][:limit]


def _sitemap_jsonld_hit(client, clf, name, careers_url, country):
    """Last resort: the careers host's own robots.txt sitemaps, with JSON-LD JobPosting on job pages."""
    host = urlsplit(careers_url).netloc
    try:
        txt = client.get(f"https://{host}/robots.txt", ok_404=True)
    except Exception:  # noqa: BLE001
        return []
    sitemaps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", txt.text if txt is not None else "")[:3]
    if not sitemaps:
        sitemaps = [f"https://{host}/sitemap.xml"]     # the standard location (fetched only if robots.txt allows)
    token = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-") + "-ld"
    opts = {"host": host, "sitemaps": sitemaps}
    res = check_feed(client, clf, name, "jsonld", token, {**opts, "_verify_limit": VERIFY_SAMPLE}, country)
    if res.get("error") or not res.get("parsed"):
        return []
    return [{"provider": "jsonld", "token": token, "opts": opts, **res, "evidence": "careers-site sitemap + JSON-LD"}]


def discover(client, clf, name, careers_url, do_probe=True, extra_tokens=(), known_urls=(), country=None):
    found, other, notes = fetch_page_scan(client, careers_url) if careers_url else ([], [], [])
    hits = []
    for provider, token, opts in found:
        opts, res = _check(client, clf, name, provider, token, opts, country)
        hits.append({"provider": provider, "token": token, "opts": opts, **(res or {}),
                     "evidence": "linked from careers page"})
    for url in known_urls:
        for provider, token, opts in scan_html(url)[0]:
            if any((h["provider"], h["token"], h["opts"]) == (provider, token, opts) for h in hits):
                continue
            opts, res = _check(client, clf, name, provider, token, opts, country)
            ok = res.get("jobs") and (res.get("focus") or _core(token) == _core(name)
                                       or _core(name).startswith(_core(token)))
            hits.append({"provider": provider, "token": token, "opts": opts, **res,
                         "evidence": "known URL, verified live" if ok else "known URL, NOT confirmed"})
            if not ok and "error" not in res:
                hits[-1]["error"] = "no Swiss postings and tenant name does not match company"
    if do_probe and not any(h.get("jobs") and not h.get("error") for h in hits):
        hits += probe(client, clf, name, extra_tokens, country)
    if careers_url and not any(h.get("jobs") and not h.get("error") for h in hits):
        hits += _sitemap_jsonld_hit(client, clf, name, careers_url, country)
    return {"name": name, "careers_url": careers_url, "hits": hits, "unsupported": other, "notes": notes}


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
