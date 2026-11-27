"""SAP SuccessFactors RMK adapter: microdata parsing, slug pre-filter and ordering (offline)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from finder.classify import Classifier
from finder.pipeline import load_config
from finder.providers import jsonld, successfactors as sf

CLF = Classifier(load_config())

PAGE = """<div class="jobDisplayShell" itemscope="itemscope"><span itemprop="jobLocation" itemscope itemtype="http://schema.org/Place">
<meta itemprop="streetAddress" content="Z&uuml;rich, CH, 8022"></span>
<meta itemprop="datePosted" content="Thu Oct 08 02:00:00 UTC 2026">
<span xml:lang="en-GB" lang="en-GB" itemprop="title" data-careersite-propertyid="title" class="x">Marketing Intern (6 months)</span>
<span itemprop="description" data-careersite-propertyid="description" class="y"><p>Join our <b>brand</b> team in Zurich.</p>
<p>You are enrolled in a Bachelor's programme; fluent German is a plus.</p>""" + ("<p>more text</p>" * 30) + """</span>
<div class="clear"></div>"""
EXPIRED = '<div class="jobTitle"> </div><div class="job"><p><strong>Thank you for your interest</strong></p></div>'


class FakeClient:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url):
        self.calls.append(url)
        r = mock.Mock(); r.text = self.pages[url]
        return r


class TestParse(unittest.TestCase):
    def setUp(self):
        sf.configure(detail_filter=lambda t, e: CLF.intern_type(t, e) is not None)

    def test_microdata(self):
        rec = sf.parse_page({}, "1234567", "https://c.example/job/Zuerich-Marketing-Intern/1234567/", PAGE)
        self.assertEqual(rec["title"], "Marketing Intern (6 months)")
        self.assertEqual((rec["locations"], rec["country_codes"], rec["posted"]), (["Zürich, CH"], ["CH"], "2026-10-08"))
        self.assertIn("brand team", rec["description"])
        self.assertNotIn("Thank you", rec["description"])

    def test_separate_address_fields_variant(self):
        page = ('<span itemprop="jobLocation"><meta itemprop="addressLocality" content="M&uuml;nchen">'
                '<meta itemprop="addressRegion" content="BY"><meta itemprop="addressCountry" content="DE"></span>'
                '<span itemprop="title">EY-Parthenon Praktikant Financial Diligence (w/m/d)</span>')
        rec = sf.parse_page({}, "1", "u", page)
        self.assertEqual((rec["locations"], rec["country_codes"]), (["München, BY, DE"], ["DE"]))
        page2 = ('<span itemprop="title">Praktikant Audit</span>'
                 '<span data-careersite-propertyid="city" class="x">Zürich   </span>')
        self.assertEqual(sf.parse_page({}, "2", "u", page2)["locations"], ["Zürich"])
        page3 = ('<h1><span itemprop="title">Praktikum Personalmarketing (m/w/d)</span></h1>'
                 '<div class="col-xs-12"><span lang="de-DE" class="rtltextaligneligible">Praktikum Personalmarketing</span>'
                 '<span xml:lang="en-US" lang="en-US" class="rtltextaligneligible">M&uuml;nster, DEU      </span></div>')
        rec3 = sf.parse_page({}, "3", "u", page3)
        self.assertEqual(rec3["locations"], ["Münster, DEU"])
        self.assertEqual(CLF.location(rec3["locations"])[0], ["DE"])

    def test_expired_page_is_no_posting(self):
        self.assertIsNone(sf.parse_page({}, "1", "u", EXPIRED))

    def test_slug_text(self):
        self.assertEqual(sf.slug_text("https://x/job/K%C3%B6ln-Software-Engineer-Zurich-&amp;-DA/123/"),
                         "Köln Software Engineer Zurich & DA")
        self.assertEqual(sf.slug_text("https://x/ey/job/Amsterdam-Marketing-Intern-1083-HP/1264493001/"),
                         "Amsterdam Marketing Intern 1083 HP")


SITEMAP = """<urlset>
<url><loc>https://c.example/job/Chicago-Underwriter-IL-60290/1000001/</loc><lastmod>2026-10-01</lastmod></url>
<url><loc>https://c.example/job/Zuerich-Senior-Actuary/1000002/</loc><lastmod>2026-10-01</lastmod></url>
<url><loc>https://c.example/job/Zuerich-Marketing-Intern/1000003/</loc><lastmod>2026-10-01</lastmod></url>
</urlset>"""


class TestFetch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        jsonld.configure(cache_dir=Path(self.tmp.name))
        sf.configure(slug_in_scope=lambda t: bool(CLF.location([t])[0]),
                     slug_priority=lambda t: CLF.intern_type(t) is not None,
                     detail_filter=lambda t, e: CLF.intern_type(t, e) is not None)
        senior = PAGE.replace("Marketing Intern (6 months)", "Senior Actuary")
        self.pages = {"https://c.example/sitemap.xml": SITEMAP,
                      "https://c.example/job/Zuerich-Senior-Actuary/1000002/": senior,
                      "https://c.example/job/Zuerich-Marketing-Intern/1000003/": PAGE}
        self.company = {"name": "Example", "token": "example-sf", "sitemaps": ["https://c.example/sitemap.xml"]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_target_country_urls_and_internships_first(self):
        c = FakeClient(self.pages)
        out = sf.fetch(c, dict(self.company, max_new=1))
        job_calls = [u for u in c.calls if "/job/" in u]
        self.assertEqual(job_calls, ["https://c.example/job/Zuerich-Marketing-Intern/1000003/"])  # Chicago never fetched
        self.assertEqual([p.title for p in out], ["Marketing Intern (6 months)"])
        self.assertEqual(out[0].provider, "successfactors")
        c2 = FakeClient(self.pages)
        out2 = sf.fetch(c2, dict(self.company, max_new=5))           # next run: the rest, intern from cache
        self.assertEqual([u for u in c2.calls if "/job/" in u], ["https://c.example/job/Zuerich-Senior-Actuary/1000002/"])
        self.assertEqual(sorted(p.title for p in out2), ["Marketing Intern (6 months)", "Senior Actuary"])

    def test_old_parser_version_is_refetched(self):
        c = FakeClient(self.pages)
        sf.fetch(c, dict(self.company, max_new=5))
        with mock.patch.object(sf, "PARSER_VERSION", sf.PARSER_VERSION + 1):
            c2 = FakeClient(self.pages)
            sf.fetch(c2, dict(self.company, max_new=5))
        self.assertEqual(len([u for u in c2.calls if "/job/" in u]), 2)   # both cached pages re-parsed


if __name__ == "__main__":
    unittest.main()
