"""Workday sitemap listing (finder/providers/workday_sitemap.py), offline."""
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from finder.classify import Classifier
from finder.pipeline import load_config
from finder.providers import jsonld, workday_sitemap as wds

CLF = Classifier(load_config())
BASE = "https://wd3.myworkdaysite.com/recruiting/mdlz/External/job/"


def sitemap(*paths):
    return "<urlset>" + "".join(f"<url><loc>{BASE}{p}</loc></url>" for p in paths) + "</urlset>"


class Client:
    def __init__(self, xml):
        self.xml, self.calls = xml, []

    def get(self, url, **kw):
        self.calls.append(url)
        r = mock.Mock(); r.text = self.xml
        return r


COMPANY = {"name": "Mondelez", "token": "mdlz-wds", "host": "wd3.myworkdaysite.com", "tenant": "mdlz", "sites": ["External"]}


class TestWorkdaySitemap(unittest.TestCase):
    def test_from_url(self):
        r = wds.from_url(BASE + "Wroclaw-Poland/Taste-the-Future---R-D-Internship--f-m-x-_R-182829-2")
        self.assertEqual(r, {"title": "Taste the Future - R D Internship f m x", "location": "Wroclaw Poland", "id": "R-182829-2"})
        r = wds.from_url(BASE + "Switzerland---Zug/Brand-Management-Intern_R-04")
        self.assertEqual((r["title"], r["location"]), ("Brand Management Intern", "Switzerland, Zug"))
        self.assertEqual(CLF.location([r["location"]])[0], ["CH"])
        self.assertEqual(CLF.location([wds.from_url(BASE + "Dublin-Ohio/Sales-Intern_R-1")["location"]])[0], [])
        self.assertIsNone(wds.from_url("https://wd3.myworkdaysite.com/recruiting/mdlz/External/introduceYourself"))

    def test_one_request_per_site_and_keep_window(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(jsonld, "_cache_dir", Path(d)):
            c = Client(sitemap("Zurich/Marketing-Intern_R-1", "London/Sales-Intern_R-2"))
            out = wds.fetch(c, COMPANY)
            self.assertEqual(len(c.calls), 1)                                 # the sitemap only, no job pages
            self.assertEqual(c.calls[0], "https://wd3.myworkdaysite.com/recruiting/mdlz/External/siteMap.xml")
            self.assertEqual(sorted(p.job_id for p in out), ["R-1", "R-2"])
            # R-1 drops out of the newest-100 list: still returned while within keep_days ...
            out = wds.fetch(Client(sitemap("London/Sales-Intern_R-2")), COMPANY)
            self.assertEqual(sorted(p.job_id for p in out), ["R-1", "R-2"])
            # ... and dropped once it was last listed more than keep_days ago
            cache = jsonld._load_cache("mdlz-wds")
            cache["R-1"]["listed"] = (date.today() - timedelta(days=31)).isoformat()
            jsonld._save_cache("mdlz-wds", cache)
            out = wds.fetch(Client(sitemap("London/Sales-Intern_R-2")), COMPANY)
            self.assertEqual([p.job_id for p in out], ["R-2"])

    def test_verify_does_not_touch_cache_and_empty_sitemap_fails(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(jsonld, "_cache_dir", Path(d)):
            wds.fetch(Client(sitemap("Zurich/Marketing-Intern_R-1")), {**COMPANY, "_verify_limit": 8})
            self.assertEqual(jsonld._load_cache("mdlz-wds"), {})
            with self.assertRaises(ValueError):
                wds.fetch(Client("<urlset></urlset>"), COMPANY)


if __name__ == "__main__":
    unittest.main()
