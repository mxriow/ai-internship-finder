"""Teamtailor career sites: the public RSS feed every Teamtailor career site publishes at /jobs.rss.

companies.yaml entry:  provider: teamtailor, token: <slug>, host: <company>.teamtailor.com (or the custom careers host)

The feed lists published jobs with their full description (HTML), publication date, department and structured
locations (city + country, in the `tt:` namespace), 100 per request; `?offset=100`, `200`, ... gives the next
ones (`page` is ignored). Most boards need one request. Teamtailor's REST API needs a customer key and is not used.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from ..models import Posting, html_to_text
from ._common import PostingList

NS = {"tt": "https://teamtailor.com/locations"}


def feed_url(token, host="", **_):
    return f"https://{host or token + '.teamtailor.com'}/jobs.rss"


def _date(value):
    try:
        return parsedate_to_datetime(value).date().isoformat() if value else None
    except (TypeError, ValueError):
        return None


def parse(xml: bytes | str, company: dict) -> PostingList:
    root = ET.fromstring(xml)
    out = PostingList()
    for item in root.iter("item"):
        t = lambda tag: (item.findtext(tag, default="", namespaces=NS) or "").strip()  # noqa: E731
        link = t("link")
        m = re.search(r"/jobs/(\d+)", link)
        job_id = m.group(1) if m else t("guid")
        locs = []
        for loc in item.findall("tt:locations/tt:location", NS):
            city = (loc.findtext("tt:city", default="", namespaces=NS) or loc.findtext("tt:name", default="", namespaces=NS) or "").strip()
            country = (loc.findtext("tt:country", default="", namespaces=NS) or "").strip()
            locs.append(", ".join(x for x in (city, country) if x))
        if t("remoteStatus") == "fully" and not locs:
            locs.append("Remote")
        out.append(Posting(provider="teamtailor", company=company["name"], token=company["token"], job_id=job_id,
                           title=t("title"), url=link, locations=[l for l in dict.fromkeys(locs) if l],
                           description=html_to_text(t("description")), posted=_date(t("pubDate")),
                           department=t("tt:department") or None))
    out.total = len(out)
    return out


PAGE, MAX_PAGES = 100, 30


def fetch(client, company):
    url = feed_url(company["token"], company.get("host", ""))
    out, seen = PostingList(), set()
    for n in range(MAX_PAGES):
        page = parse(client.get(url + (f"?offset={n * PAGE}" if n else "")).content, company)
        fresh = [p for p in page if p.job_id not in seen]
        seen.update(p.job_id for p in fresh)
        out.extend(fresh)
        if len(page) < PAGE or not fresh or company.get("_verify_limit"):
            break
    out.total = len(out)
    return out
