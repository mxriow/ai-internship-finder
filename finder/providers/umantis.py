"""Abacus Umantis career sites (recruitingapp-<n>.umantis.com): the public job list page.

companies.yaml entry:  provider: umantis, token: <slug>, host: recruitingapp-2791.umantis.com
                       (optional: list_path, default /Jobs/All)

Umantis publishes no feed; the list page is plain HTML, 10 jobs per page, and links the next page in a
`data-pagination-next-href` attribute. Each row gives the title, job link, "Online since" date and a few
labelled fields (Department, Type, Starting as) plus unlabelled ones that hold the work location
("Zurich"). robots.txt on these hosts allows the list and job pages (it disallows exports, imports and
subscriptions). Job pages are a JavaScript app without the description in the HTML, so no description
is fetched.
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from urllib.parse import urljoin

from ..models import Posting
from ._common import PostingList

MAX_PAGES = 40
_ROW = re.compile(r'<tr class="tableaslist_contentrow\d"[^>]*>(.*?)</tr>', re.S)
_LINK = re.compile(r'<a\s+href="(/Vacancies/(\d+)/Description/\d+)"[^>]*>(.*?)</a>', re.S)
_SPAN = re.compile(r"<span[^>]*>(.*?)</span>", re.S)
_POSTED = re.compile(r"(?:online since|online seit|en ligne depuis|online dal|publi\w+)\s*:?\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", re.I)
LOCATION_LABELS = re.compile(r"^(?:location|work location|ort|arbeitsort|standort|einsatzort|lieu|lieu de travail|luogo|sede|locatie)$", re.I)
EMPLOYMENT_LABELS = re.compile(r"^(?:type|starting as|einstieg als|anstellungsart|pensum|type de poste|art der anstellung)$", re.I)
DEPARTMENT_LABELS = re.compile(r"^(?:department|abteilung|bereich|fachbereich|département|division)$", re.I)


def feed_url(token, host="", list_path="/Jobs/All", **_):
    return f"https://{host}{list_path}"


def _text(fragment: str) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", t).replace("-->", "").strip(" |\xa0-")


def parse_rows(page: str):
    """Yield dicts with job_id, path, title, locations, posted, employment, department."""
    for row in _ROW.findall(page):
        link = _LINK.search(row)
        if not link:
            continue
        title = _text(link.group(3))
        rec = {"job_id": link.group(2), "path": link.group(1), "title": title, "locations": [], "posted": None,
               "employment": [], "department": None}
        for i, span in enumerate(_SPAN.findall(row)):
            text = _text(span)
            if not text or text == title or "<a" in span:
                continue
            m = _POSTED.search(text)
            if m:
                rec["posted"] = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date().isoformat()
                continue
            label, sep, value = text.partition(":")
            if sep and len(label) <= 30:
                label, value = label.strip(), value.strip()
                if LOCATION_LABELS.match(label):
                    rec["locations"].append(value)
                elif EMPLOYMENT_LABELS.match(label):
                    rec["employment"].append(value)
                elif DEPARTMENT_LABELS.match(label):
                    rec["department"] = value
                continue
            if i > 0:                          # unlabelled cells: work location, grade, unit ("Zurich")
                rec["locations"].append(text)
        yield rec


def fetch(client, company):
    host = company["host"]
    url = feed_url(company["token"], host, company.get("list_path", "/Jobs/All"))
    out, seen = PostingList(), set()
    for _ in range(MAX_PAGES):
        page = client.get(url).text
        for rec in parse_rows(page):
            if rec["job_id"] in seen:
                continue
            seen.add(rec["job_id"])
            out.append(Posting(provider="umantis", company=company["name"], token=company["token"],
                               job_id=rec["job_id"], title=rec["title"], url=f"https://{host}{rec['path']}",
                               locations=list(dict.fromkeys(rec["locations"])), posted=rec["posted"],
                               employment_raw=", ".join(rec["employment"]) or None, department=rec["department"]))
        nxt = re.search(r'data-pagination-next-href="([^"]+)"', page)
        if not nxt or company.get("_verify_limit"):
            break
        url = urljoin(url, html.unescape(nxt.group(1)).split("#")[0])
    out.total = len(out)
    return out
