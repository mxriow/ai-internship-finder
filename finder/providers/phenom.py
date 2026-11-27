"""Phenom career sites: sitemaps listed in robots.txt + schema.org JobPosting (JSON-LD) on job pages.

companies.yaml entry:  provider: phenom, token: <slug>, host: careers.example.com
                       (optional: sitemaps, sitemap_filter, prefer, max_new, budget_seconds, all_pages)

Phenom publishes one sitemap per locale (/global/en/, /de/de/, ...) listing the same jobs; the
English/global ones are used and locale copies of a job collapse by its id. Crawling, caching,
the per-run page budget and robots.txt Crawl-delay are handled by the shared crawler (jsonld.py).
Phenom job URLs end in the job title ("/job/R123/Marketing-Intern"), and boards run to thousands
of jobs (DHL ~9,000), so only pages whose title looks like an internship, working-student, trainee
or graduate role are fetched (`all_pages: true` fetches every page). Phenom's own JSON API (/api/apply) is disallowed by robots.txt on these sites and is not used.
"""
from __future__ import annotations

import html
import re
from urllib.parse import unquote

from . import _common, jsonld

DEFAULTS = {"url_filter": r"/job/", "id_pattern": r"/job/([^/]+)/", "prefer": r"/(global|int)/en/|/en/"}
LOCALE_PREFERENCE = (r"/(global|int)/en/", r"/(us|gb|uk|ch)/en/", r"/en/")


def feed_url(token, host="", **_):
    return f"https://{host}/"


def sitemaps_from_robots(client, host):
    txt = client.get(f"https://{host}/robots.txt").text
    found = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", txt)
    for pattern in LOCALE_PREFERENCE:
        chosen = [s for s in found if re.search(pattern, s)]
        if chosen:
            return chosen[:3]
    return found[:3]


def fetch(client, company):
    company = {**DEFAULTS, **company}
    if not company.get("sitemaps"):
        company["sitemaps"] = sitemaps_from_robots(client, company["host"])
        if not company["sitemaps"]:
            raise ValueError("robots.txt lists no sitemaps")
    def parse(jid, url, page):
        jp = jsonld.find_jobposting(page)
        return jsonld.to_posting(company, jid, url, jp) if jp else None

    def order(jobs):
        hot = [jid for jid, (url, _) in jobs.items() if _common.detail_filter(title_slug(url))]
        if company.get("_verify_limit"):      # discovery check: a sample of any jobs, target countries first
            return jsonld.default_order(jobs)
        if company.get("all_pages"):
            return hot + [jid for jid in jobs if jid not in set(hot)]
        return hot

    return jsonld.crawl(client, company, "phenom", parse, order)


def title_slug(url: str) -> str:
    """'.../job/R123/Marketing-Intern-m-w-d' -> 'Marketing Intern m w d'"""
    return re.sub(r"[-_]+", " ", html.unescape(unquote(url.rstrip("/").rsplit("/", 1)[-1])))
