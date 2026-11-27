import xml.etree.ElementTree as ET

from ..models import Posting, html_to_text, iso_date
from .greenhouse import _dedupe


def _base(token, domain="de"):
    return f"https://{token}.jobs.personio.{domain}"


def feed_url(token, domain="de", **_):
    return _base(token, domain) + "/xml"


def fetch(client, company):
    token, domain = company["token"], company.get("domain", "de")
    root = ET.fromstring(client.get(feed_url(token, domain)).content)
    out = []
    for p in root.iter("position"):
        t = lambda tag: (p.findtext(tag) or "").strip()
        locs = [t("office")] + [(o.text or "").strip() for o in p.findall("additionalOffices/office")]
        desc = "\n".join(html_to_text(d.findtext("value")) for d in p.findall("jobDescriptions/jobDescription"))
        out.append(Posting(
            provider="personio", company=company["name"], token=token,
            job_id=t("id"), title=t("name"),
            url=f"{_base(token, domain)}/job/{t('id')}",
            locations=_dedupe(locs), description=desc,
            posted=iso_date(t("createdAt")),
            employment_raw=" ".join(x for x in (t("employmentType"), t("seniority"), t("schedule")) if x) or None,
            department=t("department") or None,
        ))
    return out
