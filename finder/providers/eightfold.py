"""Eightfold career sites (*.eightfold.ai, or the employer's own host in front of it).

companies.yaml entry:  provider: eightfold, token: <tenant>, host: <tenant>.eightfold.ai (or custom), domain: example.com

Uses the jobs endpoint the careers page itself calls (/api/apply/v2/jobs), one query per target
country via its `location` filter. Only used where robots.txt allows /api/apply/ and the server
answers; some tenants refuse automated requests (HTTP 403) and stay in gaps.
"""
from __future__ import annotations

import html
import re

from ..models import Posting, html_to_text, iso_date
from . import _common
from ._common import PostingList

NUM, MAX_PAGES = 100, 20


def feed_url(token, host="", domain="", **_):
    return f"https://{host}/careers?domain={domain}"


def resolve(client, tenant):
    """{'host', 'domain'} for a tenant, read from its own careers page (it may redirect to a custom host)."""
    r = client.get(f"https://{tenant}.eightfold.ai/careers")
    m = re.search(r'"domain"\s*:\s*"([a-z0-9.-]+\.[a-z]{2,})"', html.unescape(r.text))
    if not m:
        raise ValueError("no domain parameter on the Eightfold careers page")
    return {"host": r.url.split("/")[2], "domain": m.group(1)}


def fetch(client, company):
    host, domain = company["host"], company["domain"]
    out, seen = PostingList(), set()
    for code, names in _common.targets.items():
        start = 0
        for _ in range(MAX_PAGES):
            d = client.get(f"https://{host}/api/apply/v2/jobs",
                           params={"domain": domain, "start": start, "num": NUM, "location": names[0]}).json()
            positions = d.get("positions") or []
            if start == 0:
                out.total += d.get("count", 0) or 0
            for p in positions:
                pid = str(p.get("id"))
                if pid in seen:
                    continue
                seen.add(pid)
                out.append(_to_posting(company, p))
            start += NUM
            if not positions or start >= (d.get("count") or 0):
                break
    return out


def _to_posting(company, p):
    title = (p.get("name") or p.get("posting_name") or "").strip()
    keep = _common.detail_filter(title, None)
    created = p.get("t_create")
    return Posting(provider="eightfold", company=company["name"], token=company["token"], job_id=str(p.get("id")),
                   title=title, url=p.get("canonicalPositionUrl") or f"https://{company['host']}/careers/job/{p.get('id')}",
                   locations=list(dict.fromkeys(p.get("locations") or [p.get("location") or ""])),
                   posted=iso_date(created * 1000) if isinstance(created, (int, float)) else None,
                   department=p.get("department") or None,
                   description=html_to_text(p.get("job_description")) if keep else "")
