from ..models import Posting, html_to_text, iso_date

API = "https://boards-api.greenhouse.io/v1/boards/{token}"


def feed_url(token, **_):
    return API.format(token=token) + "/jobs?content=true"


def board_name(client, token):
    r = client.get(API.format(token=token), ok_404=True)
    return r.json().get("name") if r is not None else None


def fetch(client, company):
    token = company["token"]
    data = client.get(feed_url(token)).json()
    out = []
    for j in data.get("jobs", []):
        locs = [(j.get("location") or {}).get("name") or ""]
        for o in j.get("offices") or []:
            locs += [o.get("name") or "", o.get("location") or ""]
        out.append(Posting(
            provider="greenhouse", company=company["name"], token=token,
            job_id=str(j["id"]), title=(j.get("title") or "").strip(),
            url=j.get("absolute_url") or "",
            locations=_dedupe(locs),
            description=html_to_text(j.get("content")),
            posted=iso_date(j.get("first_published") or j.get("updated_at")),
            department=", ".join(d.get("name", "") for d in j.get("departments") or []) or None,
            language=j.get("language"),
        ))
    return out


def _dedupe(items):
    seen, out = set(), []
    for i in items:
        i = (i or "").strip()
        if i and i.lower() not in seen:
            seen.add(i.lower())
            out.append(i)
    return out
