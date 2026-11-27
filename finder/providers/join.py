"""JOIN (join.com/companies/<company>): the company page's embedded job list + JSON-LD on job pages.

companies.yaml entry:  provider: join, token: <company>     (the slug in join.com/companies/<company>)

The public company page carries its job list in the page data (__NEXT_DATA__): title, city, country (ISO code),
employment type and creation date. The description is read from the job page's schema.org JobPosting, fetched
only for internship-like titles. join.com's robots.txt allows both pages.
"""
from __future__ import annotations

import json
import logging
import re

from ..models import Posting, html_to_text, iso_date
from . import _common, jsonld
from ._common import PostingList

log = logging.getLogger(__name__)
_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def feed_url(token, **_):
    return f"https://join.com/companies/{token}"


def jobs_from_page(page: str) -> tuple[list[dict], int | None]:
    m = _NEXT.search(page)
    if not m:
        raise ValueError("JOIN company page without job data")
    data = json.loads(m.group(1))
    jobs = (((data.get("props") or {}).get("pageProps") or {}).get("pageData") or {}).get("jobs") or {}
    total = (jobs.get("pagination") or {}).get("total") if isinstance(jobs.get("pagination"), dict) else None
    return jobs.get("items") or [], total


def fetch(client, company):
    token = company["token"]
    items, total = jobs_from_page(client.get(feed_url(token)).text)
    out = PostingList()
    for j in items:
        city, country = j.get("city") or {}, j.get("country") or {}
        place = ", ".join(x for x in (city.get("cityName"), city.get("countryName")) if x)
        p = Posting(provider="join", company=company["name"], token=token, job_id=str(j.get("id")),
                    title=(j.get("title") or "").strip(), url=f"{feed_url(token)}/{j.get('idParam')}",
                    locations=[place] if place else (["Remote"] if j.get("workplaceType") == "REMOTE" else []),
                    country_codes=[country["iso3166"].upper()] if country.get("iso3166") else [],
                    posted=iso_date(j.get("createdAt")), employment_raw=(j.get("employmentType") or {}).get("name"),
                    department=(j.get("category") or {}).get("name"))
        if _common.detail_filter(p.title, p.employment_raw) and not company.get("_verify_limit"):
            try:
                jp = jsonld.find_jobposting(client.get(p.url).text) or {}
                p.description = html_to_text(jsonld._text(jp.get("description")))
            except Exception as e:  # noqa: BLE001 - keep the list entry if the job page fails
                log.info("join details %s: %s", p.url, e)
        out.append(p)
    out.total = total or len(out)
    return out
