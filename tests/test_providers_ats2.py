"""Providers added for the gap re-discovery (Teamtailor, ...), tested offline on saved sample responses."""
import unittest
from pathlib import Path
from unittest import mock

from finder.classify import Classifier
from finder.pipeline import configure_providers, load_config
from finder.providers import bamboohr, hibob, join, teamtailor, umantis

FIX = Path(__file__).parent / "fixtures"
CFG = load_config()
CLF = Classifier(CFG)
configure_providers(CFG, CLF)


def resp(text="", content=None, url="https://x/", obj=None):
    r = mock.Mock()
    r.text = text
    r.content = content if content is not None else text.encode("utf-8")
    r.url = url
    r.json.return_value = obj
    return r


class Recorder:
    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def get(self, url, params=None, **kw):
        self.calls.append(url)
        return self.handler(url, params)

    def post_json(self, url, payload, **kw):
        self.calls.append(url)
        return self.handler(url, payload)


class TestTeamtailor(unittest.TestCase):
    def test_rss_feed(self):
        xml = (FIX / "teamtailor_jobs.rss").read_bytes()
        c = Recorder(lambda url, p: resp(content=xml))
        out = teamtailor.fetch(c, {"name": "Teamtailor", "token": "career", "host": "career.teamtailor.com"})
        self.assertEqual(c.calls, ["https://career.teamtailor.com/jobs.rss"])        # one request (under 100 jobs)
        self.assertEqual([p.job_id for p in out], ["8786914", "8746132"])
        p = out[0]
        self.assertEqual(p.title, "Integration Success Specialist")
        self.assertEqual(p.locations, ["Stockholm, Sweden"])
        self.assertEqual(p.posted, "2026-11-24")
        self.assertEqual(p.department, "Integration Operations")
        self.assertIn("Teamtailor is a global Employer Branding", p.description)
        self.assertNotIn("<p>", p.description)
        self.assertTrue(p.url.startswith("https://career.teamtailor.com/jobs/8786914"))
        self.assertEqual(out.total, 2)

    def test_pages_of_100_by_offset(self):
        def feed(start, n):
            items = "".join(f"<item><title>Job {i}</title><link>https://c.example/jobs/{i}-job</link><guid>{i}</guid></item>"
                            for i in range(start, start + n))
            return f'<rss xmlns:tt="https://teamtailor.com/locations"><channel>{items}</channel></rss>'.encode()
        pages = {"https://c.example/jobs.rss": feed(0, 100), "https://c.example/jobs.rss?offset=100": feed(100, 100),
                 "https://c.example/jobs.rss?offset=200": feed(200, 31)}
        c = Recorder(lambda url, p: resp(content=pages[url]))
        out = teamtailor.fetch(c, {"name": "Axpo", "token": "axpo", "host": "c.example"})
        self.assertEqual(len(out), 231)
        self.assertEqual(len(c.calls), 3)

    def test_target_country_and_remote(self):
        xml = b"""<?xml version="1.0"?><rss xmlns:tt="https://teamtailor.com/locations"><channel>
          <item><title>Marketing Intern</title><description>&lt;p&gt;Hi&lt;/p&gt;</description>
          <pubDate>Mon, 02 Nov 2026 09:00:00 +0100</pubDate><link>https://jobs.acme.ch/jobs/12-marketing-intern</link>
          <remoteStatus>hybrid</remoteStatus><guid>x</guid>
          <tt:locations><tt:location><tt:name>HQ</tt:name><tt:city>Baden</tt:city><tt:country>Switzerland</tt:country></tt:location></tt:locations>
          </item>
          <item><title>Sales Intern</title><description/><link>https://jobs.acme.ch/jobs/13-sales</link>
          <remoteStatus>fully</remoteStatus><guid>y</guid></item></channel></rss>"""
        out = teamtailor.parse(xml, {"name": "Acme", "token": "acme"})
        self.assertEqual(CLF.location(out[0].locations)[0], ["CH"])
        self.assertEqual(out[1].locations, ["Remote"])
        self.assertEqual(out[1].posted, None)


if __name__ == "__main__":
    unittest.main()


class TestBambooHR(unittest.TestCase):
    def test_list_and_details_only_for_internships(self):
        import json
        lst = json.loads((FIX / "bamboohr_list.json").read_text())
        lst["result"].append({"id": "40", "jobOpeningName": "Business Development Intern", "employmentStatusLabel": "Intern",
                              "location": {"city": "Luxembourg", "state": None}, "atsLocation": {"country": None}})
        detail = json.loads((FIX / "bamboohr_detail.json").read_text())

        def handler(url, params):
            return resp(obj=detail if url.endswith("/detail") else lst)
        c = Recorder(handler)
        out = bamboohr.fetch(c, {"name": "ClearSpace", "token": "clearspace"})
        self.assertEqual(c.calls[0], "https://clearspace.bamboohr.com/careers/list")
        self.assertEqual(c.calls[1:], ["https://clearspace.bamboohr.com/careers/40/detail"])   # internship only
        self.assertEqual(len(out), 4)
        self.assertEqual(out.total, 25)
        self.assertEqual(out[1].locations, ["Luxembourg"])
        self.assertEqual(CLF.location(out[1].locations)[0], ["LU"])
        intern = out[3]
        self.assertEqual(intern.url, "https://clearspace.bamboohr.com/careers/40")
        self.assertIn("At ClearSpace, we believe in reusability", intern.description)
        self.assertEqual(intern.posted, "2026-03-18")
        self.assertEqual(intern.locations, ["Luxembourg"])       # city = country: once
        self.assertEqual(out[0].description, "")


class TestDetection(unittest.TestCase):
    def test_links_to_new_systems(self):
        from finder import discover as d
        page = ('<a href="https://acme.teamtailor.com/jobs">Jobs</a> <a href="https://clearspace.bamboohr.com/careers">x</a>'
                '<iframe src="https://cembra.softgarden.io/de/vacancies"></iframe>'
                '<script src="https://career.teamtailor.com/x.js"></script> <a href="https://www.bamboohr.com/">BambooHR</a>'
                '<a href="https://emiratesjobs.avature.net/careers">x</a>')
        found, other = d.scan_html(page)
        self.assertIn(("teamtailor", "acme", {"host": "acme.teamtailor.com"}), found)
        self.assertIn(("bamboohr", "clearspace", {}), found)
        self.assertNotIn(("bamboohr", "www", {}), found)
        self.assertFalse(any(t == "career" for _, t, _ in found))              # Teamtailor's own site, not an employer
        self.assertIn(("jsonld", "cembra-so", {"host": "cembra.softgarden.io", "sitemaps": ["https://cembra.softgarden.io/sitemap.xml"],
                                               "url_filter": r"/job/\d+", "id_pattern": r"/job/(\d+)"}), found)
        self.assertIn(("jsonld", "emiratesjobs-av", {"host": "emiratesjobs.avature.net", "robots": True}), found)

    def test_teamtailor_on_own_domain(self):
        from finder import discover as d
        html = '<link rel="stylesheet" href="https://assets.teamtailor-cdn.com/assets/careersite.css">'
        self.assertIn(("teamtailor", "careers-axpo-com-te", {"host": "careers.axpo.com"}), d._marker_hits(html, "https://careers.axpo.com/jobs"))

    def test_no_quadratic_blowup_on_long_tokens(self):
        import time
        from finder import discover as d
        start = time.time()
        d.scan_html("a" * 300000 + ".x " + "-" * 300000)
        self.assertLess(time.time() - start, 2)

    def test_robots_sitemaps_only_allowed_ones(self):
        from finder import discover as d
        robots = "Sitemap: https://x.avature.net/careers/sitemap_index.xml\nSitemap: https://x.avature.net/hidden/sitemap.xml\n"
        c = Recorder(lambda url, p: resp(text=robots))
        c.allowed = lambda url: "/hidden/" not in url
        self.assertEqual(d.robots_sitemaps(c, "x.avature.net"), ["https://x.avature.net/careers/sitemap_index.xml"])


class TestUmantis(unittest.TestCase):
    def test_list_pages_and_fields(self):
        p1 = (FIX / "umantis_list_p1.html").read_text(encoding="utf-8")
        p2 = (FIX / "umantis_list_p2.html").read_text(encoding="utf-8")
        c = Recorder(lambda url, p: resp(text=p2 if "tc1152481=p2" in url else p1))
        out = umantis.fetch(c, {"name": "KPMG Switzerland", "token": "kpmg-ch", "host": "recruitingapp-2791.umantis.com"})
        self.assertEqual(c.calls, ["https://recruitingapp-2791.umantis.com/Jobs/All",
                                   "https://recruitingapp-2791.umantis.com/Jobs/All?tc1152481=p2&_search_token1152481=2009345590"])
        self.assertEqual([p.job_id for p in out], ["9378", "9332", "9232"])
        first = out[0]
        self.assertEqual(first.title, "Senior Consultant - Treasury Technology Advisory")
        self.assertEqual(first.url, "https://recruitingapp-2791.umantis.com/Vacancies/9378/Description/2")
        self.assertEqual(first.posted, "2026-11-26")
        self.assertEqual(first.department, "Audit Corporates")
        self.assertIn("Zurich", first.locations)
        self.assertEqual(CLF.location(first.locations)[0], ["CH"])
        self.assertEqual(CLF.location(out[1].locations)[0], ["CH"])          # Geneva
        self.assertEqual(CLF.intern_type(out[2].title), "intern")

    def test_verify_reads_one_page(self):
        p1 = (FIX / "umantis_list_p1.html").read_text(encoding="utf-8")
        c = Recorder(lambda url, p: resp(text=p1))
        umantis.fetch(c, {"name": "K", "token": "k", "host": "recruitingapp-1.umantis.com", "_verify_limit": 8})
        self.assertEqual(len(c.calls), 1)


class TestHiBob(unittest.TestCase):
    def test_job_ad_feed(self):
        import json
        data = json.loads((FIX / "hibob_job_ad.json").read_text(encoding="utf-8"))
        seen = {}

        def handler(url, p):
            return resp(obj=data)
        c = Recorder(handler)
        c.get = lambda url, params=None, headers=None, **kw: (seen.update(url=url, headers=headers), resp(obj=data))[1]
        out = hibob.fetch(c, {"name": "Synpulse", "token": "synpulse"})
        self.assertEqual(seen["url"], "https://synpulse.careers.hibob.com/api/job-ad")
        self.assertEqual(seen["headers"]["companyidentifier"], "synpulse")
        self.assertEqual(len(out), 4)
        first = out[0]
        self.assertEqual(first.locations, ["Bratislava, Slovakia"])
        self.assertEqual(first.posted, "2026-06-17")
        self.assertIn("Your Growth Unleashed", first.description)
        self.assertNotIn("None", first.description)
        intern = out[3]
        self.assertEqual(intern.url, "https://synpulse.careers.hibob.com/jobs/x1")
        self.assertEqual(CLF.location(intern.locations)[0], ["CH"])
        self.assertEqual(CLF.intern_type(intern.title, intern.employment_raw), "intern")
        self.assertEqual(intern.description, "Join our marketing team.")


class TestJoin(unittest.TestCase):
    def test_company_page_and_intern_details(self):
        company_page = (FIX / "join_company.html").read_text(encoding="utf-8")
        job_page = (FIX / "join_job.html").read_text(encoding="utf-8")
        c = Recorder(lambda url, p: resp(text=company_page if url.endswith("/taurusgroup") else job_page))
        out = join.fetch(c, {"name": "Taurus", "token": "taurusgroup"})
        self.assertEqual(c.calls, ["https://join.com/companies/taurusgroup",
                                   "https://join.com/companies/taurusgroup/17000001-marketing-intern-zurich"])   # intern only
        self.assertEqual(len(out), 4)
        self.assertEqual(out[0].country_codes, ["CY"])
        self.assertEqual(out[0].locations, ["Nicosia, Cyprus"])
        self.assertEqual(out[0].description, "")
        intern = out[3]
        self.assertEqual(CLF.location(intern.locations, intern.country_codes)[0], ["CH"])
        self.assertEqual(intern.posted, "2026-11-20")
        self.assertIn("About Taurus", intern.description)

    def test_page_without_data_fails_loudly(self):
        c = Recorder(lambda url, p: resp(text="<html>maintenance</html>"))
        with self.assertRaises(ValueError):
            join.fetch(c, {"name": "X", "token": "x"})


class TestMergeGap(unittest.TestCase):
    def test_keeps_specific_findings_and_extra_fields(self):
        from finder.__main__ import merge_gap
        old = {"name": "Henkel", "careers_url": "https://x", "sector": "consumer", "country": "DE", "priority": 3,
               "system": "own site: job list loads from /ajax/collection, which robots.txt disallows", "url_status": "ok"}
        e = merge_gap(old, {"name": "Henkel", "careers_url": "https://x", "country": "DE"}, "unknown / not detected", "2026-11-27")
        self.assertEqual(e["system"], old["system"])
        self.assertEqual((e["priority"], e["url_status"], e["sector"]), (3, "ok", "consumer"))
        self.assertEqual(e["recheck"], "2026-11-27: still no supported feed found")
        e = merge_gap(old, {"name": "Henkel", "country": "DE"}, "iCIMS (robots.txt disallows all bots)", "2026-11-27")
        self.assertEqual(e["system"], "iCIMS (robots.txt disallows all bots)")
        self.assertTrue(e["recheck"].startswith("2026-11-27: was 'own site"))
        self.assertEqual(e["checked_at"], "2026-11-27")

    def test_generic_label_does_not_replace_a_specific_finding(self):
        from finder.__main__ import merge_gap
        old = {"name": "Aldi Süd", "system": "SuccessFactors classic (career5.successfactors.eu, robots.txt disallows)"}
        e = merge_gap(old, {"name": "Aldi Süd"}, "SuccessFactors", "2026-11-27")
        self.assertEqual(e["system"], old["system"])
        self.assertEqual(e["recheck"], "2026-11-27: still SuccessFactors")
        e = merge_gap({"name": "B", "system": "iCIMS"}, {"name": "B"}, "iCIMS (robots.txt disallows all bots)", "2026-11-27")
        self.assertEqual(e["system"], "iCIMS (robots.txt disallows all bots)")     # the new text says more

    def test_new_gap(self):
        from finder.__main__ import merge_gap
        e = merge_gap(None, {"name": "Acme", "careers_url": "https://a", "sector": "tech"}, "unknown / not detected", "2026-11-27")
        self.assertEqual(e, {"name": "Acme", "careers_url": "https://a", "sector": "tech", "system": "unknown / not detected",
                             "checked_at": "2026-11-27"})
