"""Workday postings listed in the sitemap Workday itself publishes, without fetching job pages.

companies.yaml entry:
  provider: workday_sitemap
  token: <tenant>-wds            # cache file name
  host: wd3.myworkdaysite.com    # the tenant's wdN, on myworkdaysite.com
  tenant: mdlz
  sites: [External]              # the Workday site(s), as in the job API entry
  replaces: workday:<tenant>

Why: since 16 Nov 2026 Workday answers automated clients with a Cloudflare challenge (HTTP 429,
`cf-mitigated: challenge`, no Retry-After) on the job API and on job pages. It is not a rate limit: at one
request per 20 s only 2 of 12 job pages came through (2026-11-24). The finder does not solve challenges.
The tenant's robots.txt names this sitemap, https://wdN.myworkdaysite.com/recruiting/<tenant>/<site>/siteMap.xml,
and the sitemap itself is served normally, so it is the only request made (one per site per run).

What a sitemap URL gives: /job/<primary location>/<title>_<requisition id>. So postings here have a title
rebuilt from the URL (punctuation lost: "Sales Intern (f/m/d)" reads "Sales Intern f m d"), the primary
location, and the link; no description, posting date, pay, degree or start date. The sitemap lists only
the newest jobs (often 100), so a posting stays listed for `keep_days` (default 30) after it drops out.
"""
from __future__ import annotations

import html
import re
from datetime import date, timedelta
from urllib.parse import unquote

from ..models import Posting
from . import jsonld

KEEP_DAYS = 30
_JOB = re.compile(r"/job/([^/]+)/([^/]+)_([^_/]+)$")


def sitemap_urls(host, tenant, sites):
    return [f"https://{host}/recruiting/{tenant}/{site}/siteMap.xml" for site in sites]


def feed_url(token, host="", tenant="", sites=(), **_):
    return (sitemap_urls(host, tenant, sites) or [""])[0]


def _words(slug: str, sep: str) -> str:
    s = html.unescape(unquote(slug))
    s = re.sub(r"-{3,}", "\x00", s).replace("--", " ").replace("-", " ").replace("\x00", sep)
    return re.sub(r"\s+", " ", s).strip(" ,-")


def from_url(url: str) -> dict | None:
    """'.../job/Basel-Switzerland/Marketing-Intern--f-m-d-_R-123' -> title, location, id."""
    m = _JOB.search(url)
    if not m:
        return None
    return {"title": _words(m.group(2), " - "), "location": _words(m.group(1), ", "), "id": m.group(3)}


def fetch(client, company):
    sites = company.get("sites") or []
    sitemaps = company.get("sitemaps") or sitemap_urls(company["host"], company["tenant"], sites)
    today = date.today().isoformat()
    keep_from = (date.today() - timedelta(days=int(company.get("keep_days", KEEP_DAYS)))).isoformat()
    listed = {}
    for sm in sitemaps:
        for kind, loc, _ in jsonld._entries(client.get(sm).text):
            rec = from_url(loc) if kind == "url" else None
            if rec:
                listed[rec["id"]] = {**rec, "url": loc}
    if not listed:
        raise ValueError("Workday sitemap lists no job URLs")
    verify = bool(company.get("_verify_limit"))
    cache = {} if verify else jsonld._load_cache(company["token"])
    for jid, rec in listed.items():
        cache[jid] = {**rec, "first": (cache.get(jid) or {}).get("first", today), "listed": today}
    cache = {jid: e for jid, e in cache.items() if e.get("listed", "") >= keep_from}   # older: treated as closed
    if not verify:
        jsonld._save_cache(company["token"], cache)
    out = jsonld.PostingList()
    out.total = len(listed)
    for jid, e in cache.items():
        out.append(Posting(provider="workday_sitemap", company=company["name"], token=company["token"], job_id=jid,
                           title=e["title"], url=e["url"], locations=[e["location"]] if e.get("location") else []))
    return out
