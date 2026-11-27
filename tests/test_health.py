"""Daily-run health check (finder/health.py)."""
import unittest

from finder import health

PREV = {"run_at": "2026-11-03T05:20:00+00:00", "companies": 187, "companies_ok": 186, "matched": 1700, "failed": []}


def cur(**kw):
    return {**PREV, "run_at": "2026-11-04T05:20:00+00:00", **kw}


class TestHealth(unittest.TestCase):
    def test_healthy(self):
        self.assertEqual(health.check(PREV, cur(), {"tests": "success", "run": "success", "publish": "success"}), [])

    def test_failed_step(self):
        p = health.check(PREV, cur(), {"tests": "failure", "run": "skipped"})
        self.assertEqual(len(p), 1)
        self.assertIn("tests", p[0])

    def test_more_than_ten_percent_of_feeds_failed(self):
        failed = [{"company": f"C{i}", "provider": "workday", "error": "HTTP 500"} for i in range(20)]
        self.assertEqual(health.check(PREV, cur(companies_ok=187 - 18, failed=failed[:18])), [])   # 9.6%
        p = health.check(PREV, cur(companies_ok=187 - 20, failed=failed))
        self.assertTrue(any("20 of 187 feeds failed" in x for x in p))

    def test_internships_drop(self):
        self.assertEqual(health.check(PREV, cur(matched=1100)), [])          # -35%
        p = health.check(PREV, cur(matched=1000))                            # -41%
        self.assertTrue(any("dropped from 1700 to 1000" in x for x in p))

    def test_missing_or_unchanged_summary(self):
        self.assertTrue(health.check(PREV, None))
        self.assertTrue(any("not updated" in x for x in health.check(PREV, dict(PREV))))

    def test_known_blocked_provider_is_ignored(self):
        wd = [{"company": f"W{i}", "provider": "workday", "error": "HTTP 429"} for i in range(90)]
        prev = {**PREV, "companies": 217, "companies_ok": 217,
                "per_company": [{"provider": "workday", "matched": 600}, {"provider": "greenhouse", "matched": 800}]}
        now = cur(companies=217, companies_ok=127, failed=wd, matched=800,
                  per_company=[{"provider": "workday", "matched": 0}, {"provider": "greenhouse", "matched": 800}])
        self.assertEqual(health.check(prev, now, known_blocked={"workday"}), [])
        self.assertTrue(health.check(prev, now))                       # without the setting it still alarms
        other = now["failed"] + [{"company": f"G{i}", "provider": "greenhouse", "error": "x"} for i in range(20)]
        self.assertTrue(health.check(prev, cur(**{**now, "failed": other, "companies_ok": 107}), known_blocked={"workday"}))

    def test_blocked_feeds_compared_like_with_like(self):
        # The 2026-11-24 run: 232 feeds, 58 Workday feeds blocked (HTTP 429), and companies_ok inflated by
        # retired feeds (204). Before the fix, 232-58 = 174 < 204 made the failed share negative: no alarm ever.
        wd = [{"company": f"W{i}", "provider": "workday", "error": "HTTP 429"} for i in range(58)]
        base = dict(companies=232, companies_ok=204, matched=1700)
        self.assertEqual(health.check(PREV, cur(**base, failed=wd), known_blocked={"workday"}), [])
        # 17 other feeds failing = 17 of 174 = 9.8%: below the limit
        g17 = [{"company": f"G{i}", "provider": "greenhouse", "error": "HTTP 500"} for i in range(17)]
        self.assertEqual(health.check(PREV, cur(**base, failed=wd + g17), known_blocked={"workday"}), [])
        # 18 other feeds failing = 18 of 174 = 10.3%: the alert fires, naming the non-Workday feeds
        g18 = g17 + [{"company": "G17", "provider": "jsonld", "error": "timeout"}]
        p = health.check(PREV, cur(**base, failed=wd + g18), known_blocked={"workday"})
        self.assertEqual(len(p), 1)
        self.assertIn("18 of 174 feeds failed", p[0])
        self.assertIn("58 known-blocked feeds not counted", p[0])
        self.assertNotIn("W0", p[0])

    def test_report_text(self):
        text = health.report(["Step **run** ended with `failure`."], cur(), "https://github.com/x/y/actions/runs/1")
        self.assertIn("Troubleshooting", text)
        self.assertIn("actions/runs/1", text)


if __name__ == "__main__":
    unittest.main()
