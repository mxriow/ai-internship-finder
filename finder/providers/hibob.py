"""HiBob career sites (<company>.careers.hibob.com): the public job-ad JSON the careers page itself loads.

companies.yaml entry:  provider: hibob, token: <company>     (the subdomain)

One request per run: /api/job-ad returns every published job with its site ("Zurich, Switzerland"), country,
department, employment type, publication date and the description (HTML: description, responsibilities,
requirements, benefits). The page sends the subdomain as a `companyidentifier` header; no key or login.
"""
from __future__ import annotations

from ..models import Posting, html_to_text, iso_date
from ._common import PostingList


def feed_url(token, **_):
    return f"https://{token}.careers.hibob.com/api/job-ad"


def _clean(v):
    return v if isinstance(v, str) and v not in ("None", "null") else ""


def fetch(client, company):
    token = company["token"]
    data = client.get(feed_url(token), headers={"companyidentifier": token, "Accept": "application/json"}).json()
    out = PostingList()
    for j in data.get("jobAdDetails") or []:
        site, country = _clean(j.get("site")), _clean(j.get("country"))
        loc = site if not country or country.lower() in site.lower() else f"{site}, {country}"
        text = "\n".join(html_to_text(_clean(j.get(k))) for k in ("description", "responsibilities", "requirements", "benefits")
                         if _clean(j.get(k)))
        out.append(Posting(provider="hibob", company=company["name"], token=token, job_id=str(j.get("id")),
                           title=(j.get("title") or "").strip(), url=f"https://{token}.careers.hibob.com/jobs/{j.get('id')}",
                           locations=[loc] if loc else [], description=text, posted=iso_date(_clean(j.get("publishedAt")) or None),
                           employment_raw=_clean(j.get("employmentType")) or None, department=_clean(j.get("department")) or None,
                           language=(_clean(j.get("language")) or "").upper() or None))
    out.total = len(out)
    return out
