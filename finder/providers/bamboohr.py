"""BambooHR career sites (<company>.bamboohr.com/careers): the public JSON the careers page itself loads.

companies.yaml entry:  provider: bamboohr, token: <company>     (the subdomain)

/careers/list gives every opening with title, department, employment status and city/state/country.
The description comes from /careers/<id>/detail, fetched only for internship-like titles (one request each).
"""
from __future__ import annotations

import logging

from ..models import Posting, html_to_text, iso_date
from . import _common
from ._common import PostingList

log = logging.getLogger(__name__)


def feed_url(token, **_):
    return f"https://{token}.bamboohr.com/careers/list"


def _place(loc: dict | None, ats: dict | None) -> str:
    loc, ats = loc or {}, ats or {}
    parts = [loc.get("city") or ats.get("city"), loc.get("state") or ats.get("state") or ats.get("province"),
             loc.get("addressCountry") or ats.get("country")]
    return ", ".join(dict.fromkeys(p for p in parts if p))


def fetch(client, company):
    token = company["token"]
    base = f"https://{token}.bamboohr.com/careers"
    data = client.get(feed_url(token), headers={"Accept": "application/json"}).json()
    out = PostingList()
    for j in data.get("result") or []:
        jid = str(j.get("id"))
        p = Posting(provider="bamboohr", company=company["name"], token=token, job_id=jid,
                    title=(j.get("jobOpeningName") or "").strip(), url=f"{base}/{jid}",
                    locations=[x for x in [_place(j.get("location"), j.get("atsLocation"))] if x]
                    or (["Remote"] if j.get("isRemote") else []),
                    employment_raw=j.get("employmentStatusLabel"), department=j.get("departmentLabel") or None)
        if _common.detail_filter(p.title, p.employment_raw) and not company.get("_verify_limit"):
            try:
                d = (client.get(f"{base}/{jid}/detail", headers={"Accept": "application/json"}).json()
                     .get("result") or {}).get("jobOpening") or {}
                p.description = html_to_text(d.get("description"))
                p.posted = iso_date(d.get("datePosted"))
                place = _place(d.get("location"), d.get("atsLocation"))
                if place:
                    p.locations = [place]
            except Exception as e:  # noqa: BLE001 - keep the list entry if details fail
                log.info("bamboohr details %s/%s: %s", token, jid, e)
        out.append(p)
    out.total = (data.get("meta") or {}).get("totalCount") or len(out)
    return out
