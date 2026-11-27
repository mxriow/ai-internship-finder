"""SAP SuccessFactors Recruiting Marketing (RMK) career sites: sitemap.xml + schema.org microdata.

companies.yaml entry:
  provider: successfactors
  token: <slug, used for ids and the cache file>
  host: careers.example.com
  sitemaps: [https://careers.example.com/sitemap.xml]
  url_filter: '/job/'               # optional (default '/job/')
  id_pattern: '/(\\d{6,})/?$'        # optional (default: the numeric id at the end)

RMK job URLs start with the place ("/job/Zuerich-Marketing-Intern/1234567/"), so URLs are
pre-filtered by the same location rules as everything else and only target-country pages are
fetched; internship-looking URLs go first. Pages are cached and re-fetched only when the
sitemap's <lastmod> changes (shared crawler in jsonld.py). The RMK RSS feed is not used: robots.txt
disallows it on these sites.
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from urllib.parse import unquote

from ..models import html_to_text
from . import jsonld

PARSER_VERSION = 2   # bump when parse_page changes: cached pages from older versions are re-fetched
DEFAULTS = {"url_filter": r"/job/", "id_pattern": r"/(\d{6,})/?(?:[?#].*)?$"}

_slug_in_scope = lambda text: True        # noqa: E731  set by configure(): target-country place in slug
_slug_priority = lambda text: False       # noqa: E731  set by configure(): looks like an internship
_detail_filter = lambda title, employment: True  # noqa: E731


def configure(slug_in_scope=None, slug_priority=None, detail_filter=None):
    global _slug_in_scope, _slug_priority, _detail_filter
    _slug_in_scope = slug_in_scope or _slug_in_scope
    _slug_priority = slug_priority or _slug_priority
    _detail_filter = detail_filter or _detail_filter


def feed_url(token, sitemaps=(), **_):
    return (sitemaps or [""])[0]


def slug_text(url: str) -> str:
    """'/job/K%C3%B6ln-Marketing-Intern/123/' -> 'Köln Marketing Intern'"""
    m = re.search(r"/job/([^/]+)/", url)
    return re.sub(r"[-_]+", " ", html.unescape(unquote(m.group(1)))) if m else ""


def _prop(page, name):
    m = re.search(r'<meta[^>]*itemprop="%s"[^>]*content="([^"]*)"' % name, page)
    if m:
        return html.unescape(m.group(1)).strip()
    m = re.search(r'<[^>]*itemprop="%s"[^>]*>([^<]*)' % name, page)
    return html.unescape(m.group(1)).strip() if m else ""


def _careersite(page, prop):
    m = re.search(r'data-careersite-propertyid="%s"[^>]*>([^<]*)' % prop, page)
    return html.unescape(m.group(1)).strip() if m else ""


def _date(value):
    for fmt in ("%a %b %d %H:%M:%S %Z %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _description(page):
    i = page.find('itemprop="description"')
    if i < 0:
        return ""
    seg = page[page.find(">", i) + 1: i + 60000]
    end = min([j for j in (seg.find("</span>\n"), seg.find('<div class="clear')) if j > 200] or [len(seg)])
    return html_to_text(seg[:end])


def parse_page(company, jid, url, page):
    title = _prop(page, "title")
    if not title:
        return None                        # expired job ("no longer available") or not a job page
    address = _prop(page, "streetAddress")   # "Zürich, CH, 8002" / "Amsterdam, NL, 1083 HP"
    parts = [p.strip() for p in address.split(",") if p.strip()][:2]
    country = parts[1] if len(parts) > 1 else ""      # "City, CC, zip": the 2nd part is the country
    if not parts:                            # other RMK template: separate address fields / a "city" property
        country = _prop(page, "addressCountry") or _careersite(page, "country")
        parts = [x for x in (_prop(page, "addressLocality") or _careersite(page, "city"),
                             _prop(page, "addressRegion"), country) if x]
    if not parts:                            # third template (e.g. BASF): only a plain "Münster, DEU" line
        m = re.search(r'class="rtltextaligneligible">\s*([^<,]{2,60}, [A-Z]{3})\s*</span>', page)
        parts = [html.unescape(m.group(1))] if m else []
    codes = [country.upper()] if re.fullmatch(r"[A-Za-z]{2}", country) else []
    location = ", ".join(parts)
    keep = _detail_filter(title, None)
    return {"job_id": jid, "title": title, "url": url, "locations": [location] if location else [],
            "country_codes": codes, "posted": _date(_prop(page, "datePosted") or ""),
            "employment_raw": None, "department": _prop(page, "industry") or None,
            "valid_through": _date(_prop(page, "validThrough") or ""),
            "description": _description(page) if keep else ""}


def fetch(client, company):
    company = {**DEFAULTS, **company}

    def order(jobs):
        scoped = [jid for jid, (url, _) in jobs.items() if _slug_in_scope(slug_text(url))]
        return sorted(scoped, key=lambda jid: not _slug_priority(slug_text(jobs[jid][0])))   # internships first

    return jsonld.crawl(client, company, "successfactors",
                        lambda jid, url, page: parse_page(company, jid, url, page), order, version=PARSER_VERSION)
