"""Generic sitemap + schema.org JobPosting provider (offline, with a fake client)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from finder.providers import jsonld


def page(obj):
    return f'<html><head><script type="application/ld+json">{json.dumps(obj)}</script></head></html>'


JP = {"@context": "https://schema.org", "@type": "JobPosting", "title": "Marketing Intern (6 months)",
      "datePosted": "2026-10-20", "employmentType": "INTERN", "description": "<p>Join our <b>brand</b> team.</p>",
      "jobLocation": {"@type": "Place", "address": {"addressLocality": "Zürich", "addressCountry": "CH"}}}


class FakeClient:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url):
        self.calls.append(url)
        r = mock.Mock(); r.text = self.pages[url]
        return r


class TestParsing(unittest.TestCase):
    def test_graph_list_and_single(self):
        self.assertEqual(jsonld.find_jobposting(page({"@graph": [{"@type": "WebPage"}, JP]}))["title"], JP["title"])
        self.assertEqual(jsonld.find_jobposting(page([{"@type": "Organization"}, JP]))["title"], JP["title"])
        self.assertIsNone(jsonld.find_jobposting(page({"@type": "WebPage"})))
        self.assertIsNone(jsonld.find_jobposting('<script type="application/ld+json">{broken</script>'))

    def test_locations(self):
        jp = {"jobLocation": [{"address": {"addressLocality": "Amsterdam", "addressCountry": {"name": "Netherlands"}}},
                              {"address": {"addressLocality": "Basel", "addressRegion": "BS", "addressCountry": "CH"}}]}
        locs, codes = jsonld.locations_of(jp)
        self.assertEqual(locs, ["Amsterdam, Netherlands", "Basel, BS, CH"])
        self.assertEqual(codes, ["CH"])
        self.assertEqual(jsonld.locations_of({"jobLocationType": "TELECOMMUTE"}), (["Remote"], []))


SITEMAP_INDEX = """<sitemapindex><sitemap><loc>https://c.example/global/en/sitemap1.xml</loc></sitemap>
<sitemap><loc>https://c.example/fr/fr/sitemap1.xml</loc></sitemap></sitemapindex>"""
SITEMAP_EN = """<urlset><url><loc>https://c.example/global/en/job/111/Marketing-Intern</loc><lastmod>2026-10-20</lastmod></url>
<url><loc>https://c.example/global/en/job/222/Data-Engineer</loc><lastmod>2026-10-20</lastmod></url>
<url><loc>https://c.example/global/en/about-us</loc></url></urlset>"""


class TestFetch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        jsonld.configure(cache_dir=Path(self.tmp.name), detail_filter=lambda t, e: "Intern" in t)
        self.company = {"name": "Example", "token": "example", "sitemaps": ["https://c.example/sitemap_index.xml"],
                        "sitemap_filter": "/global/en/", "url_filter": "/job/", "id_pattern": r"/job/([^/]+)/"}
        expired = dict(JP, title="Old Intern", validThrough="2020-01-01")
        self.pages = {"https://c.example/sitemap_index.xml": SITEMAP_INDEX,
                      "https://c.example/global/en/sitemap1.xml": SITEMAP_EN,
                      "https://c.example/global/en/job/111/Marketing-Intern": page(JP),
                      "https://c.example/global/en/job/222/Data-Engineer": page(expired)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_fetch_filters_dedupes_and_caches(self):
        c = FakeClient(self.pages)
        out = jsonld.fetch(c, self.company)
        self.assertNotIn("https://c.example/fr/fr/sitemap1.xml", c.calls)          # sitemap_filter
        self.assertEqual([p.title for p in out], ["Marketing Intern (6 months)"])   # expired one skipped
        p = out[0]
        self.assertEqual((p.job_id, p.locations, p.country_codes, p.employment_raw), ("111", ["Zürich, CH"], ["CH"], "INTERN"))
        self.assertIn("brand", p.description)                                        # kept: intern-like title
        self.assertEqual(out.total, 2)
        c2 = FakeClient(self.pages)
        jsonld.fetch(c2, self.company)                                               # second run: from cache
        self.assertFalse(any("/job/" in u for u in c2.calls))

    def test_crawl_delay_budget_caps_new_pages(self):
        c = FakeClient(self.pages)
        c._interval = lambda url: 5.0                                   # robots.txt Crawl-delay: 5
        jsonld.fetch(c, dict(self.company, budget_seconds=5))           # budget for exactly one page
        self.assertEqual(sum("/job/" in u for u in c.calls), 1)

    def test_prefer_collapses_locale_duplicates(self):
        sm = """<urlset><url><loc>https://c.example/de/de/job/111/Praktikum</loc></url>
        <url><loc>https://c.example/global/en/job/111/Marketing-Intern</loc></url></urlset>"""
        c = FakeClient({"https://c.example/s.xml": sm})
        jobs = jsonld.collect_urls(c, {"sitemaps": ["https://c.example/s.xml"], "url_filter": "/job/",
                                       "id_pattern": r"/job/([^/]+)/", "prefer": "/en/"})
        self.assertEqual(jobs, {"111": ("https://c.example/global/en/job/111/Marketing-Intern", None)})


if __name__ == "__main__":
    unittest.main()
