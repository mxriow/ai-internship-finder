from ..models import Posting, html_to_text, iso_date
from .greenhouse import _dedupe

HOSTS = {"global": "https://api.lever.co", "eu": "https://api.eu.lever.co"}


def feed_url(token, region="global", **_):
    return f"{HOSTS[region]}/v0/postings/{token}?mode=json"


def fetch(client, company):
    token = company["token"]
    data = client.get(feed_url(token, company.get("region", "global"))).json()
    out = []
    for j in data:
        cat = j.get("categories") or {}
        locs = [cat.get("location") or ""] + list(cat.get("allLocations") or [])
        desc = "\n".join(filter(None, [j.get("descriptionPlain"), j.get("additionalPlain")]
                                + [l.get("text", "") + " " + html_to_text(l.get("content", ""))
                                   for l in j.get("lists") or []]))
        out.append(Posting(
            provider="lever", company=company["name"], token=token,
            job_id=j["id"], title=(j.get("text") or "").strip(),
            url=j.get("hostedUrl") or "", apply_url=j.get("applyUrl"),
            locations=_dedupe(locs),
            country_codes=[j["country"].upper()] if j.get("country") else [],
            description=desc, posted=iso_date(j.get("createdAt")),
            employment_raw=cat.get("commitment"),
            department=cat.get("team") or cat.get("department"),
        ))
    return out

