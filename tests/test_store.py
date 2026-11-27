import unittest

from finder import store


def rec(i, company="greenhouse:acme"):
    return {"id": f"{company}:{i}", "title": f"Intern {i}", "company": "Acme"}


class TestMerge(unittest.TestCase):
    def test_new_and_closing_after_two_misses(self):
        db = {"jobs": {}}
        ok = {"greenhouse:acme"}
        new = store.merge(db, [rec(1), rec(2)], ok, "2026-10-01", "t1")
        self.assertEqual(sorted(new), ["greenhouse:acme:1", "greenhouse:acme:2"])
        store.merge(db, [rec(1)], ok, "2026-10-02", "t2")          # job 2 missed once
        self.assertEqual(db["jobs"]["greenhouse:acme:2"]["status"], "open")
        store.merge(db, [rec(1)], ok, "2026-10-03", "t3")          # missed twice -> closed
        self.assertEqual(db["jobs"]["greenhouse:acme:2"]["status"], "closed")
        self.assertEqual(db["jobs"]["greenhouse:acme:1"]["first_seen"], "2026-10-01")
        self.assertEqual(db["jobs"]["greenhouse:acme:1"]["last_seen"], "2026-10-03")

    def test_reappearing_job_resets_misses(self):
        db = {"jobs": {}}
        ok = {"greenhouse:acme"}
        store.merge(db, [rec(1)], ok, "d1", "t")
        store.merge(db, [], ok, "d2", "t")
        new = store.merge(db, [rec(1)], ok, "d3", "t")
        self.assertEqual(new, [])
        self.assertEqual((db["jobs"]["greenhouse:acme:1"]["status"], db["jobs"]["greenhouse:acme:1"]["missed"]), ("open", 0))

    def test_failed_company_keeps_previous_data(self):
        db = {"jobs": {}}
        store.merge(db, [rec(1), rec(1, "lever:beta")], {"greenhouse:acme", "lever:beta"}, "d1", "t")
        for day in ("d2", "d3", "d4"):  # lever:beta feed fails three times
            store.merge(db, [rec(1)], {"greenhouse:acme"}, day, "t")
        job = db["jobs"]["lever:beta:1"]
        self.assertEqual((job["status"], job["missed"], job["last_seen"]), ("open", 0, "d1"))


class TestDedupe(unittest.TestCase):
    def test_identical_title_company_location_collapse(self):
        a = {"id": "workday:db:2", "company": "Deutsche Bank", "title": "Intern (Luxembourg)", "locations": ["Luxembourg"]}
        b = {"id": "workday:db:1", "company": "Deutsche Bank", "title": "Intern  (luxembourg) ", "locations": ["luxembourg"]}
        c = {"id": "workday:db:3", "company": "Deutsche Bank", "title": "Intern (Luxembourg)", "locations": ["Frankfurt"]}
        kept, dropped = store.dedupe([a, b, c])
        self.assertEqual(sorted(r["id"] for r in kept), ["workday:db:1", "workday:db:3"])
        self.assertEqual(dropped, {"workday:db:2"})
        self.assertEqual(next(r for r in kept if r["id"] == "workday:db:1")["duplicates"], ["workday:db:2"])


class TestPipelineResilience(unittest.TestCase):
    def test_failing_feed_is_skipped(self):
        from finder import pipeline
        from finder.providers import PROVIDERS

        class Boom:
            @staticmethod
            def fetch(client, company):
                raise RuntimeError("HTTP 500")
        PROVIDERS["boom"] = Boom
        try:
            out = pipeline.fetch_all(None, [{"name": "X", "provider": "boom", "token": "x"}], workers=1)
        finally:
            del PROVIDERS["boom"]
        self.assertEqual(out[0][1], [])
        self.assertIn("HTTP 500", out[0][2])


if __name__ == "__main__":
    unittest.main()


class TestReplacedFeed(unittest.TestCase):
    def test_old_feed_postings_close_once_replacement_works(self):
        from finder.pipeline import retire_replaced
        db = {"jobs": {"workday:abbott:X_1": {"id": "workday:abbott:X_1", "status": "open", "missed": 0}}}
        comps = [{"provider": "jsonld", "token": "abbott-site", "replaces": "workday:abbott"}]
        self.assertEqual(retire_replaced(comps, set()), set())            # new feed failed: old postings untouched
        ok = retire_replaced(comps, {"jsonld:abbott-site"})
        self.assertIn("workday:abbott", ok)
        for day in ("2026-11-19", "2026-11-20"):
            store.merge(db, [], ok, day, day + "T05:00:00+00:00")
        self.assertEqual(db["jobs"]["workday:abbott:X_1"]["status"], "closed")
