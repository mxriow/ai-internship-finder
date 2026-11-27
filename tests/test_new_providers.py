"""Oracle Recruiting Cloud, Eightfold, Taleo and Phenom providers + their detection (offline)."""
import json
import unittest
from pathlib import Path
from unittest import mock

from finder import discover as d
from finder.classify import Classifier
from finder.pipeline import configure_providers, load_config
from finder.providers import _common, eightfold, oracle, phenom, taleo

CFG = load_config()
CLF = Classifier(CFG)
configure_providers(CFG, CLF)


def resp(obj=None, text=None, url="https://x/"):
    r = mock.Mock()
    r.json.return_value = obj
    r.text = text if text is not None else json.dumps(obj)
    r.url = url
    return r


class Recorder:
    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def get(self, url, params=None, **kw):
        self.calls.append((url, params))
        return self.handler("GET", url, params, None)

    def post_json(self, url, payload, headers=None, **kw):
        self.calls.append((url, payload))
        return self.handler("POST", url, payload, headers)


class TestOracle(unittest.TestCase):
    def test_paging_codes_and_details_only_for_target_internships(self):
        reqs = [{"Id": "1", "Title": "Marketing Intern", "PrimaryLocation": "Zug, Switzerland", "PrimaryLocationCountry": "CH",
                 "PostedDate": "2026-10-20", "secondaryLocations": []},
                {"Id": "2", "Title": "Marketing Intern", "PrimaryLocation": "Atlanta, United States", "PrimaryLocationCountry": "US",
                 "secondaryLocations": []},
                {"Id": "3", "Title": "Senior Engineer", "PrimaryLocation": "London, United Kingdom", "PrimaryLocationCountry": "GB",
                 "secondaryLocations": [{"Name": "Zurich, Switzerland", "CountryCode": "CH"}]}]

        def handler(method, url, params, headers):
            if "recruitingCEJobRequisitionDetails" in url:
                return resp({"items": [{"ExternalDescriptionStr": "<p>Bachelor students welcome.</p>"}]})
            return resp({"items": [{"TotalJobsCount": 3, "requisitionList": reqs}]})
        c = Recorder(handler)
        out = oracle.fetch(c, {"name": "Acme", "token": "acme", "host": "abc.fa.ocs.oraclecloud.com", "site": "CX_1"})
        self.assertEqual([p.job_id for p in out], ["1", "2", "3"])
        self.assertEqual(out[2].locations, ["London, United Kingdom", "Zurich, Switzerland"])
        self.assertEqual(out[2].country_codes, ["GB", "CH"])
        detail_calls = [u for u, _ in c.calls if "Details" in u]
        self.assertEqual(len(detail_calls), 1)                   # only the CH internship, not the US one
        self.assertIn('Id="1"', detail_calls[0])
        self.assertIn("Bachelor students", out[0].description)
        self.assertTrue(out[0].url.endswith("/sites/CX_1/job/1"))


class TestEightfold(unittest.TestCase):
    def test_resolve_reads_escaped_domain(self):
        page = '<script>{&#34;domain&#34;: &#34;mlp.com&#34;, &#34;user&#34;: &#34;&#34;}</script>'
        c = Recorder(lambda *a: resp(text=page, url="https://career.mlp.com/careers"))
        self.assertEqual(eightfold.resolve(c, "mlp"), {"host": "career.mlp.com", "domain": "mlp.com"})

    def test_one_query_per_country_dedupes(self):
        pos = {"id": 7, "name": "Investment Intern", "locations": ["Geneva, Switzerland", "London, United Kingdom"],
               "t_create": 1792972800, "canonicalPositionUrl": "https://mlp.eightfold.ai/careers/job/7",
               "job_description": "<p>Summer internship.</p>"}
        c = Recorder(lambda m, u, params, h: resp({"count": 1, "positions": [pos]}))
        out = eightfold.fetch(c, {"name": "Millennium", "token": "mlp", "host": "career.mlp.com", "domain": "mlp.com"})
        self.assertEqual(len(out), 1)                                  # same job from the CH and UK queries
        self.assertEqual(len(c.calls), len(_common.targets))           # one query per target country
        self.assertEqual({p["location"] for _, p in c.calls}, {v[0] for v in _common.targets.values()})
        self.assertEqual(out[0].posted, "2026-10-26")
        self.assertIn("Summer internship", out[0].description)


class TestTaleo(unittest.TestCase):
    def test_portal_columns_and_paging(self):
        page1 = {"pagingData": {"totalCount": 2, "pageSize": 1}, "requisitionList": [
            {"jobId": "256066", "contestNo": "17456", "column": ["Partnerships Lead", '["United Kingdom-London-London Luton Airport"]'], "locationsColumns": [1]}]}
        page2 = {"pagingData": {"totalCount": 2, "pageSize": 1}, "requisitionList": [
            {"jobId": "256067", "contestNo": "17457", "column": ["Commercial Intern", '["Switzerland-Geneva-Geneva Airport"]'], "locationsColumns": [1]}]}

        detail = (Path(__file__).parent / "fixtures" / "taleo_jobdetail.html").read_text(encoding="utf-8")

        def handler(method, url, payload, headers):
            if method == "GET":
                return resp(text=detail if "jobdetail.ftl" in url else "var portal = '101430233';")
            self.assertEqual(headers.get("tzname"), "Europe/Zurich")
            return resp(page1 if payload["pageNo"] == 1 else page2)
        c = Recorder(handler)
        out = taleo.fetch(c, {"name": "easyJet", "token": "easyjet", "host": "easyjet.taleo.net", "section": "2"})
        self.assertEqual([p.job_id for p in out], ["17456", "17457"])
        details = [u for u, _ in c.calls if "jobdetail.ftl" in u]
        self.assertEqual(details, ["https://easyjet.taleo.net/careersection/2/jobdetail.ftl?job=17457&lang=en"])  # intern only
        self.assertEqual(out[0].description, "")
        self.assertIn("digital merchandising expertise", out[1].description)   # saved detail page (fixture)
        self.assertIn("Apply now.", out[1].description)
        self.assertNotIn("%3C", out[1].description)
        self.assertEqual(out[1].locations, ["Switzerland, Geneva, Geneva Airport"])
        self.assertEqual(CLF.location(out[1].locations)[0], ["CH"])
        self.assertTrue(out[0].url.endswith("jobdetail.ftl?job=17456&lang=en"))
        self.assertIn("portal=101430233", c.calls[1][0])

    def test_description_from_detail_page_without_field(self):
        self.assertEqual(taleo.description_from_detail("<html>no history</html>"), "")


class TestPhenom(unittest.TestCase):
    def test_prefers_global_english_sitemaps(self):
        robots = ("Sitemap: https://c.example/ca/fr/sitemap_index.xml\nSitemap: https://c.example/global/en/sitemap_index.xml\n"
                  "Sitemap: https://c.example/de/de/sitemap_index.xml\n")
        c = Recorder(lambda *a: resp(text=robots))
        self.assertEqual(phenom.sitemaps_from_robots(c, "c.example"), ["https://c.example/global/en/sitemap_index.xml"])


class TestPhenomCrawl(unittest.TestCase):
    def test_fetches_only_internship_title_pages(self):
        sm = ("<urlset><url><loc>https://c.example/global/en/job/R1/Marketing-Intern-m-w-d</loc></url>"
              "<url><loc>https://c.example/global/en/job/R2/Warehouse-Operator</loc></url></urlset>")
        page = ('<script type="application/ld+json">{"@type":"JobPosting","title":"Marketing Intern (m/w/d)",'
                '"jobLocation":{"address":{"addressLocality":"Bonn","addressCountry":"DE"}}}</script>')
        c = Recorder(lambda m, url, p, h: resp(text=sm if url.endswith(".xml") else page))
        with mock.patch.object(phenom.jsonld, "_cache_dir", None):
            out = phenom.fetch(c, {"name": "DHL", "token": "dhl-ph", "host": "c.example",
                                   "sitemaps": ["https://c.example/global/en/sitemap.xml"]})
        self.assertEqual([p.job_id for p in out], ["R1"])
        self.assertEqual(out.total, 2)
        self.assertFalse(any("Warehouse" in u for u, _ in c.calls))
        self.assertEqual(out[0].provider, "phenom")


class TestSitemapOrder(unittest.TestCase):
    def test_target_country_internships_first(self):
        urls = ["https://c.example/job/manager-communications-in-dubai-uae-jid-1",
                "https://c.example/job/senior-engineer-in-kuala-lumpur-malaysia-jid-2",
                "https://c.example/job/intern-design-in-barcelona-spain-jid-3",
                "https://c.example/job/working-student-marketing-in-berlin-germany-jid-4",
                "https://c.example/job/senior-pm-in-berlin-germany-jid-5"]
        jobs = {str(i): (u, None) for i, u in enumerate(urls, 1)}
        self.assertEqual(phenom.jsonld.default_order(jobs), ["4", "1", "5", "3", "2"])


class TestDetection(unittest.TestCase):
    def test_links(self):
        html = ('<a href="https://ibqbjb.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs">x</a>'
                '<a href="https://easyjet.taleo.net/careersection/2/jobsearch.ftl">y</a>'
                '<a href="https://morganstanley.eightfold.ai/careers">z</a><a href="https://app.eightfold.ai/careers?domain=x">w</a>')
        found = {(p, t): o for p, t, o in d.scan_html(html)[0]}
        self.assertEqual(found[("oracle", "ibqbjb")], {"host": "ibqbjb.fa.ocs.oraclecloud.com", "site": "CX_1"})
        self.assertEqual(found[("taleo", "easyjet")], {"host": "easyjet.taleo.net", "section": "2"})
        self.assertIn(("eightfold", "morganstanley"), found)
        self.assertNotIn(("eightfold", "app"), found)

    def test_page_markers(self):
        hits = d._marker_hits('<script src="https://cdn.phenompeople.com/CareerConnectResources/x.js">', "https://careers.abb/global/en")
        self.assertEqual(hits, [("phenom", "careers-abb-ph", {"host": "careers.abb"})])
        hits = d._marker_hits('<link href="//rmkcdn.successfactors.com/a.css">', "https://jobs.example.de/")
        self.assertEqual(hits[0][0], "successfactors")
        self.assertEqual(hits[0][2]["sitemaps"], ["https://jobs.example.de/sitemap.xml"])


if __name__ == "__main__":
    unittest.main()
