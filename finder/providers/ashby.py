from ..models import Posting, iso_date
from .greenhouse import _dedupe

API = "https://api.ashbyhq.com/posting-api/job-board/{token}"


def feed_url(token, **_):
    return API.format(token=token)


def _addr(a):
    pa = (a or {}).get("postalAddress") or {}
    return [x for x in (pa.get("addressLocality"), pa.get("addressRegion"), pa.get("addressCountry")) if x]


def fetch(client, company):
    token = company["token"]
    data = client.get(feed_url(token)).json()
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location") or "", ", ".join(_addr(j.get("address")))]
        for s in j.get("secondaryLocations") or []:
            locs += [s.get("location") or "", ", ".join(_addr(s.get("address")))]
        out.append(Posting(
            provider="ashby", company=company["name"], token=token,
            job_id=j["id"], title=(j.get("title") or "").strip(),
            url=j.get("jobUrl") or "", apply_url=j.get("applyUrl"),
            locations=_dedupe(locs), description=j.get("descriptionPlain") or "",
            posted=iso_date(j.get("publishedAt")), employment_raw=j.get("employmentType"),
            department=j.get("department"),
        ))
    return out
