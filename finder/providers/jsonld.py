"""Generic provider: a careers site's sitemap + schema.org JobPosting (JSON-LD) on each job page.

companies.yaml entry (all regexes optional except where noted):
  provider: jsonld
  token: <slug, used for ids and the cache file>
  host: careers.example.com
  sitemaps: [https://careers.example.com/sitemap.xml]   # sitemap(s) or sitemap index(es); required
  sitemap_filter: '/global/en/'     # which child/locale sitemaps to follow
  url_filter: '/job/'               # which URLs are job pages
  id_pattern: '/job/([^/]+)'        # job id (one group); collapses locale duplicates of one job
  prefer: '/en'                     # among duplicates, prefer URLs matching this
  max_new: 300                      # at most this many new/changed pages fetched per run
  budget_seconds: 480               # ...and no more than fit in this time at the host's allowed pace

Politeness: every request goes through PoliteClient (robots.txt, per-host rate limit). Job pages
are cached in data/cache/jsonld/<token>.json and fetched again only when the sitemap's <lastmod>
changes; pages without JobPosting data are retried after 14 days. When a site has more new pages
than one run fetches, pages whose URL names a target-country place or an internship go first.
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ..models import Posting, html_to_text, iso_date

log = logging.getLogger(__name__)

MAX_SITEMAPS = 60
DEFAULT_MAX_NEW = 300
DEFAULT_BUDGET_SECONDS = 480   # per employer per run; with a robots.txt Crawl-delay this caps new pages
RETRY_NO_DATA_DAYS = 14

_cache_dir: Path | None = None
_detail_filter = lambda title, employment: True  # noqa: E731
_url_in_scope = lambda text: False     # noqa: E731  set by configure(): a target-country place in the URL
_url_priority = lambda text: False     # noqa: E731  set by configure(): the URL looks like an internship


def configure(cache_dir: Path | None = None, detail_filter=None, url_in_scope=None, url_priority=None):
    global _cache_dir, _detail_filter, _url_in_scope, _url_priority
    _cache_dir = cache_dir
    if detail_filter:
        _detail_filter = detail_filter
    _url_in_scope = url_in_scope or _url_in_scope
    _url_priority = url_priority or _url_priority


def url_text(url: str) -> str:
    """'https://x/job/intern-marketing-in-berlin-germany-jid-1' -> 'job intern marketing in berlin germany jid 1'"""
    path = html.unescape(unquote(urlsplit(url).path))
    return re.sub(r"[-_/+.]+", " ", path).strip()


def default_order(jobs):
    """Most useful pages first, so the per-run budget (and a discovery sample) goes to them: internships
    in a target country, then other target-country jobs, then other internships, then the rest. Many
    sites put the title and place in the URL; where they don't, this keeps the sitemap order."""
    def key(jid):
        text = url_text(jobs[jid][0])
        scope, prio = _url_in_scope(text), _url_priority(text)
        return (not (scope and prio), not scope, not prio)
    return sorted(jobs, key=key)


class PostingList(list):
    total = 0


def feed_url(token, sitemaps=(), **_):
    return (sitemaps or [""])[0]


# ------------------------------------------------------------------ sitemap
_LOC = re.compile(r"<(sitemap|url)>(.*?)</\1>", re.S | re.I)


def _entries(xml: str):
    """Yield (kind, loc, lastmod) for <sitemap> and <url> elements."""
    for kind, body in _LOC.findall(xml):
        loc = re.search(r"<loc>\s*(.*?)\s*</loc>", body, re.S | re.I)
        if loc:
            lm = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", body, re.S | re.I)
            yield kind.lower(), html.unescape(loc.group(1)), (lm.group(1) if lm else None)


def collect_urls(client, company) -> dict[str, tuple[str, str | None]]:
    """job_id -> (url, lastmod), following sitemap indexes."""
    sm_filter = re.compile(company["sitemap_filter"], re.I) if company.get("sitemap_filter") else None
    url_filter = re.compile(company.get("url_filter") or r"/jobs?/|/job-|/stellen|/offres?/|/vacatures?/", re.I)
    id_rx = re.compile(company.get("id_pattern") or r"(\d{4,}|[0-9a-f]{8}-[0-9a-f-]{27})(?:[/?#].*)?$", re.I)
    prefer = re.compile(company["prefer"], re.I) if company.get("prefer") else None
    queue, seen_sm, jobs = list(company["sitemaps"]), set(), {}
    while queue and len(seen_sm) < MAX_SITEMAPS:
        sm = queue.pop(0)
        if sm in seen_sm:
            continue
        seen_sm.add(sm)
        xml = client.get(sm).text
        for kind, loc, lastmod in _entries(xml):
            if kind == "sitemap":
                if not sm_filter or sm_filter.search(loc):
                    queue.append(loc)
                continue
            if not url_filter.search(loc):
                continue
            m = id_rx.search(loc)
            jid = m.group(1) if m else hashlib.sha1(loc.encode()).hexdigest()[:12]
            if jid not in jobs or (prefer and prefer.search(loc) and not prefer.search(jobs[jid][0])):
                jobs[jid] = (loc, lastmod)
    return jobs


# ------------------------------------------------------------------ JobPosting parsing
_LD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)


def _walk(node):
    if isinstance(node, list):
        for x in node:
            yield from _walk(x)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                yield from _walk(node[key])


def find_jobposting(page: str) -> dict | None:
    for block in _LD.findall(page):
        try:
            data = json.loads(html.unescape(block.strip()), strict=False)
        except ValueError:
            continue
        for node in _walk(data):
            t = node.get("@type")
            if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                return node
    return None


def _text(v) -> str:
    if isinstance(v, dict):
        return str(v.get("name") or v.get("@value") or "")
    if isinstance(v, list):
        return ", ".join(_text(x) for x in v if x)
    return html.unescape(str(v or "")).strip()


def locations_of(jp: dict) -> tuple[list[str], list[str]]:
    locs, codes = [], []
    places = jp.get("jobLocation") or []
    for place in places if isinstance(places, list) else [places]:
        addrs = place.get("address") if isinstance(place, dict) else place
        for a in addrs if isinstance(addrs, list) else [addrs]:
            if isinstance(a, str):
                locs.append(a.strip())
                continue
            if not isinstance(a, dict):
                continue
            country = _text(a.get("addressCountry"))
            parts = [_text(a.get("addressLocality")), _text(a.get("addressRegion")), country]
            locs.append(", ".join(p for p in parts if p))
            if re.fullmatch(r"[A-Za-z]{2}", country):
                codes.append(country.upper())
    if str(jp.get("jobLocationType", "")).upper() == "TELECOMMUTE" and not locs:
        locs.append("Remote")
    return [l for l in dict.fromkeys(locs) if l], codes


def to_posting(company, jid, url, jp) -> dict:
    title = _text(jp.get("title"))
    employment = _text(jp.get("employmentType")) or None
    locs, codes = locations_of(jp)
    keep_desc = _detail_filter(title, employment)
    return {"job_id": jid, "title": title, "url": _text(jp.get("url")) or url, "locations": locs,
            "country_codes": codes, "posted": iso_date(_text(jp.get("datePosted")) or None),
            "employment_raw": employment, "department": _text(jp.get("occupationalCategory")) or None,
            "valid_through": iso_date(_text(jp.get("validThrough")) or None),
            "description": html_to_text(_text(jp.get("description"))) if keep_desc else ""}


# ------------------------------------------------------------------ cache + fetch
def _cache_path(token):
    return (_cache_dir / f"{re.sub(r'[^a-z0-9_-]', '_', token.lower())}.json") if _cache_dir else None


def _load_cache(token) -> dict:
    p = _cache_path(token)
    if p and p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            log.warning("jsonld cache for %s unreadable; starting fresh", token)
    return {}


def _save_cache(token, cache):
    p = _cache_path(token)
    if p:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


def fetch(client, company):
    def parse(jid, url, page):
        jp = find_jobposting(page)
        return to_posting(company, jid, url, jp) if jp else None
    return crawl(client, company, "jsonld", parse)


def crawl(client, company, provider, parse, order=None, version=1):
    """Shared sitemap crawler: cache, per-run page budget, robots.txt pace.

    parse(jid, url, page) -> posting dict or None.
    order(jobs) -> job ids to consider, most important first (default: all, sitemap order);
    ids it leaves out are neither fetched nor returned.
    """
    token = company["token"]
    jobs = collect_urls(client, company)
    ids = order(jobs) if order else default_order(jobs)
    cache = _load_cache(token)
    # Pages parsed by an older parser version go first, so a parser fix reaches cached jobs quickly.
    ids = sorted(ids, key=lambda jid: (cache.get(jid) or {}).get("v", 1) == version)
    today = date.today()
    max_new = int(company.get("_verify_limit") or company.get("max_new") or DEFAULT_MAX_NEW)
    if ids and not company.get("_verify_limit"):
        # Respect the host's pace (rate limit or robots.txt Crawl-delay): a slow site fills its cache over
        # several runs instead of stretching one run past the workflow timeout.
        interval = client._interval(jobs[ids[0]][0]) if hasattr(client, "_interval") else 0
        if interval:
            budget = float(company.get("budget_seconds") or DEFAULT_BUDGET_SECONDS)
            max_new = min(max_new, max(1, int(budget / interval)))
    out, fetched = PostingList(), 0
    out.total = len(jobs)
    for jid in ids:
        url, lastmod = jobs[jid]
        entry = cache.get(jid)
        fresh = entry and entry.get("lastmod") == lastmod and entry.get("v", 1) == version and (
            entry.get("posting") or entry.get("checked", "") >= (today - timedelta(days=RETRY_NO_DATA_DAYS)).isoformat())
        if not fresh:
            if fetched >= max_new:
                continue                    # picked up on a later run
            fetched += 1
            try:
                page = client.get(url).text
            except Exception as e:  # noqa: BLE001 - one broken page must not fail the company
                log.info("%s %s: %s", provider, url, e)
                continue
            entry = {"lastmod": lastmod, "checked": today.isoformat(), "v": version, "posting": parse(jid, url, page)}
            cache[jid] = entry
        rec = entry.get("posting")
        if not rec or (rec.get("valid_through") and rec["valid_through"] < today.isoformat()):
            continue
        out.append(Posting(provider=provider, company=company["name"], token=token, job_id=jid,
                           title=rec["title"], url=rec["url"], locations=rec["locations"],
                           country_codes=rec["country_codes"], description=rec.get("description") or "",
                           posted=rec.get("posted"), employment_raw=rec.get("employment_raw"),
                           department=rec.get("department")))
    for jid in [k for k in cache if k not in jobs]:
        del cache[jid]                      # gone from the sitemap: posting closed
    if not company.get("_verify_limit"):
        _save_cache(token, cache)
    log.info("%s %s: %d job URLs, %d considered, %d fetched this run, %d postings",
             provider, token, len(jobs), len(ids), fetched, len(out))
    return out
