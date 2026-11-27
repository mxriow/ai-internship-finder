"""Oracle Taleo (classic career sections, <tenant>.taleo.net/careersection/<section>/).

companies.yaml entry:  provider: taleo, token: <tenant>, host: <tenant>.taleo.net, section: "2"

Uses the job-board search endpoint the career section page itself calls; the portal id is read
from the section's own jobsearch page. Listings give title and locations. For internship-like titles
only, the job's own detail page (jobdetail.ftl) is fetched once: Taleo puts the description there,
URL-encoded, in the hidden `initialHistory` field ("!|!"-separated values; the HTML values are the
description and qualifications).
"""
from __future__ import annotations

import html
import json
import logging
import re
from urllib.parse import unquote

from ..models import Posting, html_to_text
from . import _common
from ._common import PostingList

log = logging.getLogger(__name__)

MAX_PAGES = 40
HEADERS = {"tz": "GMT+01:00", "tzname": "Europe/Zurich", "X-Requested-With": "XMLHttpRequest"}
BODY = {"multilineEnabled": False, "sortingSelection": {"sortBySelectionParam": "3", "ascendingSortingOrder": "false"},
        "fieldData": {"fields": {"KEYWORD": "", "LOCATION": ""}, "valid": True},
        "filterSelectionParam": {"searchFilterSelections": [{"id": i, "selectedValues": []} for i in ("POSTING_DATE", "LOCATION", "JOB_FIELD")]},
        "advancedSearchFiltersSelectionParam": {"searchFilterSelections": [{"id": i, "selectedValues": []} for i in (
            "ORGANIZATION", "LOCATION", "JOB_FIELD", "JOB_SCHEDULE", "STUDY_LEVEL", "WILL_TRAVEL", "JOB_SHIFT")]}}


def feed_url(token, host="", section="", **_):
    return f"https://{host}/careersection/{section}/jobsearch.ftl"


def portal_id(client, host, section):
    page = client.get(f"https://{host}/careersection/{section}/jobsearch.ftl?lang=en").text
    m = re.search(r'portal["\']?\s*[:=]\s*["\']?(\d{6,})', page)
    if not m:
        raise ValueError("no portal id on the Taleo jobsearch page")
    return m.group(1)


def _locations(cell):
    try:
        val = json.loads(cell)
        return [str(x) for x in (val if isinstance(val, list) else [val])]
    except (ValueError, TypeError):
        return [cell] if cell else []


def description_from_detail(page: str) -> str:
    """The job description from a jobdetail.ftl page ('' when not found)."""
    m = re.search(r'id="initialHistory"\s+value="([^"]*)"', page) or re.search(r'name="initialHistory"[^>]*value="([^"]*)"', page)
    if not m:
        return ""
    fields = [unquote(f).replace("\\:", ":") for f in html.unescape(m.group(1)).split("!|!")]
    parts = []                       # description, then qualifications; Taleo repeats each value once
    for f in fields:
        f = f.removeprefix("!*!")
        if "<" in f and ">" in f and f not in parts:
            parts.append(f)
    return "\n".join(html_to_text(f) for f in parts).strip()


def fetch(client, company):
    host, section = company["host"], str(company["section"])
    portal = company.get("portal") or portal_id(client, host, section)
    out, page = PostingList(), 1
    while page <= MAX_PAGES:
        d = client.post_json(f"https://{host}/careersection/rest/jobboard/searchjobs?lang=en&portal={portal}",
                             {**BODY, "pageNo": page}, headers=HEADERS).json()
        reqs = d.get("requisitionList") or []
        paging = d.get("pagingData") or {}
        out.total = paging.get("totalCount", 0) or 0
        for r in reqs:
            cols = r.get("column") or []
            locs_idx = (r.get("locationsColumns") or [1])[0]
            contest = r.get("contestNo") or r.get("jobId")
            p = Posting(provider="taleo", company=company["name"], token=company["token"], job_id=str(contest),
                        title=(cols[0] if cols else "").strip(),
                        url=f"https://{host}/careersection/{section}/jobdetail.ftl?job={contest}&lang=en",
                        locations=[l.replace("-", ", ", 2) for l in _locations(cols[locs_idx] if len(cols) > locs_idx else "")])
            if _common.detail_filter(p.title, None) and not company.get("_verify_limit"):
                try:
                    p.description = description_from_detail(client.get(p.url).text)
                except Exception as e:  # noqa: BLE001 - keep the list entry if the detail page fails
                    log.info("taleo details %s: %s", p.url, e)
            out.append(p)
        if not reqs or page * (paging.get("pageSize") or len(reqs)) >= out.total:
            break
        page += 1
    return out
