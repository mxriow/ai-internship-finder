"""Oracle Recruiting Cloud (Fusion HCM "Candidate Experience" career sites).

companies.yaml entry:  provider: oracle, token: <slug>, host: <pod>.fa.<dc>.oraclecloud.com, site: CX_1

Uses the public requisitions endpoint the career site itself calls anonymously
(/hcmRestApi/resources/latest/recruitingCEJobRequisitions), 200 per page. Full descriptions come
from the requisition-details endpoint, fetched only for internship-like titles in target countries.
"""
from __future__ import annotations

import logging

from ..models import Posting, html_to_text, iso_date
from . import _common
from ._common import PostingList

log = logging.getLogger(__name__)
PAGE, MAX_PAGES = 200, 40


def feed_url(token, host="", site="", **_):
    return f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}"


def _api(host):
    return f"https://{host}/hcmRestApi/resources/latest"


def fetch(client, company):
    host, site = company["host"], company["site"]
    out, offset = PostingList(), 0
    while True:
        url = (f"{_api(host)}/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations"
               f"&finder=findReqs;siteNumber={site},limit={PAGE},offset={offset},sortBy=POSTING_DATES_DESC")
        item = (client.get(url).json().get("items") or [{}])[0]
        reqs = item.get("requisitionList") or []
        out.total = item.get("TotalJobsCount", 0) or 0
        for r in reqs:
            out.append(_to_posting(client, company, r))
        offset += PAGE
        if not reqs or offset >= out.total or offset >= PAGE * MAX_PAGES:
            return out


def _to_posting(client, company, r):
    host, site, rid = company["host"], company["site"], str(r.get("Id"))
    secondary = r.get("secondaryLocations") or []
    locations = [r.get("PrimaryLocation") or ""] + [s.get("Name") or "" for s in secondary]
    codes = [r.get("PrimaryLocationCountry") or ""] + [s.get("CountryCode") or "" for s in secondary]
    p = Posting(provider="oracle", company=company["name"], token=company["token"], job_id=rid,
                title=(r.get("Title") or "").strip(), url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{rid}",
                locations=[l for l in dict.fromkeys(locations) if l], country_codes=[c.upper() for c in codes if c],
                posted=iso_date(r.get("PostedDate")), employment_raw=r.get("ContractType") or r.get("JobSchedule"),
                department=r.get("JobFamily") or r.get("JobFunction"), description=r.get("ShortDescriptionStr") or "")
    if (_common.detail_filter(p.title, p.employment_raw) and set(p.country_codes) & _common.target_codes):
        try:
            url = (f"{_api(host)}/recruitingCEJobRequisitionDetails?expand=all&onlyData=true"
                   f'&finder=ById;Id="{rid}",siteNumber={site}')
            d = (client.get(url).json().get("items") or [{}])[0]
            p.description = html_to_text(" ".join(d.get(k) or "" for k in (
                "ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr"))) or p.description
        except Exception as e:  # noqa: BLE001 - keep the list entry if details fail
            log.info("oracle details %s: %s", rid, e)
    return p
