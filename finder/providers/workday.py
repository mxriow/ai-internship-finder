"""Workday career sites (the public, unauthenticated JSON API behind *.myworkdayjobs.com).

companies.yaml entry:  provider: workday, token: <tenant>, host: <tenant>.wd3.myworkdayjobs.com, site: <Site>

Strategy, to keep requests low: read the tenant's country facet and list only
postings in the target countries; fetch job details only for titles that look
like internships (set via configure()).
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from ..models import Posting, html_to_text, iso_date

PAGE = 20          # Workday caps page size at 20
MAX_PAGES = 60     # safety cap when a tenant has no country facet

_targets: dict[str, list[str]] = {}   # country code -> names, e.g. {"CH": ["Switzerland", "Schweiz"]}
_detail_filter = lambda title: True  # noqa: E731


def configure(targets: dict[str, list[str]], detail_filter=None):
    global _targets, _detail_filter
    _targets = targets
    if detail_filter:
        _detail_filter = detail_filter


class PostingList(list):
    total = 0   # all postings on the board, any country (used by verify)


def api_base(host, tenant, site):
    return f"https://{host}/wday/cxs/{tenant}/{site}"


def feed_url(token, host="", site="", **_):
    return f"https://{host}/{site}"


def _country_values(facets, names):
    """Find (facetParameter, [value ids]) for a country in possibly nested facets."""
    want = {n.lower() for n in names}
    for f in facets or []:
        vals = f.get("values") or []
        if vals and "facetParameter" in vals[0]:          # nested group, e.g. locationMainGroup
            hit = _country_values(vals, names)
            if hit:
                return hit
            continue
        if "country" in (f.get("facetParameter") or "").lower():
            ids = [v["id"] for v in vals if (v.get("descriptor") or "").lower() in want]
            return (f["facetParameter"], ids)
    return None


def _posted(text):
    t = (text or "").lower()
    if "today" in t:
        return date.today().isoformat()
    if "yesterday" in t:
        return (date.today() - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\s+days? ago", t)
    if m and "+" not in t:
        return (date.today() - timedelta(days=int(m.group(1)))).isoformat()
    return None


def _page(client, base, facets, offset):
    r = client.post_json(base + "/jobs", {"appliedFacets": facets, "limit": PAGE, "offset": offset, "searchText": ""})
    try:
        return r.json()
    except ValueError:
        raise RuntimeError("Workday answered with a non-JSON page (tenant outage or maintenance)") from None


def fetch(client, company):
    """All sites of one tenant: `site` plus optional `extra_sites` (e.g. a campus/internship site).

    A posting listed on several sites is kept once (first site wins), so ids stay stable.
    """
    out, seen_ids = PostingList(), set()
    for site in [company["site"], *company.get("extra_sites", [])]:
        postings, total = _fetch_site(client, company, site)
        out.total += total
        for p in postings:
            if p.job_id not in seen_ids:
                seen_ids.add(p.job_id)
                out.append(p)
    return out


def _fetch_site(client, company, site):
    tenant, host = company["token"], company["host"]
    base = api_base(host, tenant, site)
    first = _page(client, base, {}, 0)
    out = []

    plans = []   # (country code or None, facets)
    for code, names in _targets.items():
        hit = _country_values(first.get("facets"), names)
        if hit and hit[1]:
            plans.append((code, {hit[0]: hit[1]}))
        elif hit is None and (None, {}) not in plans:
            plans.append((None, {}))          # no country facet: scan everything once, filter later
    seen = set()
    for code, facets in plans:
        data = first if not facets else _page(client, base, facets, 0)
        total, offset = data.get("total", 0), 0
        while True:
            for j in data.get("jobPostings", []):
                path = j.get("externalPath") or ""
                if not path or path in seen:
                    continue
                seen.add(path)
                out.append(_to_posting(client, company, base, j, code, site))
            offset += PAGE
            if offset >= total or not data.get("jobPostings") or offset >= PAGE * MAX_PAGES:
                break
            data = _page(client, base, facets, offset)
    return out, first.get("total", 0)


def _to_posting(client, company, base, j, code, site):
    host, path = company["host"], j["externalPath"]
    p = Posting(
        provider="workday", company=company["name"], token=company["token"],
        job_id=path.rsplit("/", 1)[-1], title=(j.get("title") or "").strip(),
        url=f"https://{host}/{site}{path}",
        locations=[j.get("locationsText") or ""], country_codes=[code] if code else [],
        posted=_posted(j.get("postedOn")),
    )
    if _detail_filter(p.title):
        try:
            info = client.get(base + path).json().get("jobPostingInfo", {})
        except Exception:  # noqa: BLE001 - keep the list entry even if details fail
            return p
        p.description = html_to_text(info.get("jobDescription"))
        p.locations = [x for x in [info.get("location")] + list(info.get("additionalLocations") or []) if x] or p.locations
        country = (info.get("country") or {}).get("descriptor")
        if country:
            p.locations.append(country)
        p.employment_raw = info.get("timeType")
        p.posted = iso_date(info.get("startDate")) or p.posted
        p.url = info.get("externalUrl") or p.url
    return p
