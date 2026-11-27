"""SmartRecruiters Posting API.

NOTE: as of 2026-10 api.smartrecruiters.com/robots.txt disallows all user agents
except LinkedInBot, so PoliteClient refuses these requests. Kept so it works
automatically if that policy changes, and so discover can identify such companies.
"""
from ..models import Posting, iso_date

API = "https://api.smartrecruiters.com/v1/companies/{token}/postings"


def feed_url(token, **_):
    return API.format(token=token)


def fetch(client, company):
    token, out, offset = company["token"], [], 0
    while True:
        data = client.get(feed_url(token), params={"limit": 100, "offset": offset}).json()
        for j in data.get("content", []):
            loc = j.get("location") or {}
            out.append(Posting(
                provider="smartrecruiters", company=company["name"], token=token,
                job_id=str(j["id"]), title=(j.get("name") or "").strip(),
                url=f"https://jobs.smartrecruiters.com/{token}/{j['id']}",
                locations=[loc.get("fullLocation") or ", ".join(
                    x for x in (loc.get("city"), loc.get("country")) if x)],
                country_codes=[loc["country"].upper()] if loc.get("country") else [],
                posted=iso_date(j.get("releasedDate")),
                employment_raw=(j.get("typeOfEmployment") or {}).get("label"),
                department=(j.get("function") or {}).get("label"),
            ))
        offset += 100
        if offset >= data.get("totalFound", 0) or not data.get("content"):
            return out
