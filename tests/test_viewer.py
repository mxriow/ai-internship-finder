import json
import tempfile
import unittest
from pathlib import Path

from finder import viewer


def page_data(html: str) -> dict:
    raw = html.split('<script id="jobs-data" type="application/json">', 1)[1].split("</script>", 1)[0]
    return json.loads(raw)


DB = {"generated_at": "2026-10-23T10:00:00+00:00", "jobs": {
    "greenhouse:a:1": {"title": "Marketing Intern", "company": "Acme", "category": "marketing", "status": "open",
                       "countries": ["CH"], "url": "https://x/1"},
    "greenhouse:a:2": {"title": "Sales Intern", "company": "Acme", "category": "sales", "status": "open",
                       "countries": ["NL"], "url": "https://x/2"},
    "lever:b:3": {"title": "Brand Intern </script><script>alert(1)</script>", "company": "Beta", "category": "brand",
                  "status": "open", "countries": ["AE"], "url": "https://x/3"},
    "lever:c:4": {"title": "HR Intern", "company": "Gamma", "category": "hr", "status": "open",
                  "countries": ["LU"], "url": "https://x/4"},
}}


class TestViewerBuild(unittest.TestCase):
    def build(self, state=None, raw=None):
        with tempfile.TemporaryDirectory() as d:
            out, us = Path(d) / "index.html", Path(d) / "user_state.json"
            if state is not None:
                us.write_text(json.dumps(state))
            if raw is not None:
                us.write_text(raw)
            info = viewer.build(DB, out, user_state=us, default_categories=["marketing"], countries=["CH", "NL"])
            return info, out.read_text(encoding="utf-8")

    def test_embeds_data_and_config(self):
        info, html = self.build()
        data = page_data(html)
        self.assertEqual(len(data["jobs"]), 4)
        self.assertEqual(data["config"]["default_categories"], ["marketing"])
        self.assertEqual(data["config"]["countries"], ["CH", "NL"])
        self.assertNotIn("fetch(", html)          # self-contained: no network loads

    def test_script_breakout_is_neutralised(self):
        _, html = self.build()
        self.assertEqual(html.count("</script>"), 3)   # only the page's own three script tags (code, jobs, descriptions)
        self.assertIn("alert(1)", page_data(html)["jobs"]["lever:b:3"]["title"])

    def test_user_state_hides_and_marks(self):
        info, html = self.build({"hidden": ["greenhouse:a:2"], "hidden_companies": ["Gamma"],
                                 "starred": ["greenhouse:a:1"], "applied": ["lever:b:3"]})
        jobs = page_data(html)["jobs"]
        self.assertEqual(sorted(jobs), ["greenhouse:a:1", "lever:b:3"])
        self.assertTrue(jobs["greenhouse:a:1"]["starred"])
        self.assertFalse(jobs["greenhouse:a:1"]["applied"])
        self.assertTrue(jobs["lever:b:3"]["applied"])
        self.assertEqual(info["removed_by_user_state"], 2)

    def test_malformed_user_state_is_ignored(self):
        for raw in ["{not json", "[1, 2]", '{"hidden": 5}', ""]:
            with self.subTest(raw=raw):
                info, html = self.build(raw=raw)
                self.assertEqual(len(page_data(html)["jobs"]), 4)


if __name__ == "__main__":
    unittest.main()
