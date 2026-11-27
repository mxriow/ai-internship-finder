from ..models import Posting, html_to_text, iso_date
from .greenhouse import _dedupe


def feed_url(token, **_):
    return f"https://{token}.recruitee.com/api/offers/"


def fetch(client, company):
    token = company["token"]
    data = client.get(feed_url(token)).json()
    out = []
    for j in data.get("offers", []):
        locs = [j.get("location") or ""]
        codes = [j.get("country_code") or ""]
        for l in j.get("locations") or []:
            locs.append(", ".join(x for x in (l.get("city"), l.get("country")) if x))
            codes.append(l.get("country_code") or "")
        out.append(Posting(
            provider="recruitee", company=company["name"], token=token,
            job_id=str(j["id"]), title=(j.get("title") or "").strip(),
            url=j.get("careers_url") or "", apply_url=j.get("careers_apply_url"),
            locations=_dedupe(locs), country_codes=sorted({c.upper() for c in codes if c}),
            description=html_to_text((j.get("description") or "") + " " + (j.get("requirements") or "")),
            posted=iso_date(j.get("published_at") or j.get("created_at")),
            employment_raw=j.get("employment_type_code"),
            department=j.get("department"),
        ))
    return out
