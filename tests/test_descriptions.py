"""Description archive (data/descriptions), deadline parsing, and the viewer's embedded descriptions."""
import base64
import gzip
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from finder import descriptions, pipeline, viewer
from finder.dates import parse_deadline
from finder.models import Posting

REF = date(2026, 11, 26)


def unpack(chunks):
    out = {}
    for c in chunks:
        out.update(json.loads(gzip.decompress(base64.b64decode(c)).decode("utf-8")))
    return out


def desc_chunks(html):
    raw = html.split('<script id="desc-data" type="application/json">', 1)[1].split("</script>", 1)[0]
    return json.loads(raw)


class TestArchive(unittest.TestCase):
    def test_new_refresh_keep_and_empty_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            a = descriptions.Archive(Path(d))
            self.assertEqual(a.update("greenhouse:acme:1", "  Marketing intern.\r\n\n\n\nBachelor students.  ", "2026-11-01"), "new")
            self.assertIsNone(a.update("greenhouse:acme:1", "Marketing intern.\n\nBachelor students.", "2026-11-02"))  # same after normalising
            self.assertIsNone(a.update("greenhouse:acme:1", "", "2026-11-03"))           # empty never overwrites
            a.save()
            shard = json.loads((Path(d) / "greenhouse" / "acme.json").read_text())
            self.assertEqual(shard["1"], {"text": "Marketing intern.\n\nBachelor students.", "saved": "2026-11-01", "updated": "2026-11-01"})
            b = descriptions.Archive(Path(d))                                             # a later run
            self.assertEqual(b.update("greenhouse:acme:1", "New text", "2026-11-05"), "updated")
            b.save()
            shard = json.loads((Path(d) / "greenhouse" / "acme.json").read_text())
            self.assertEqual(shard["1"], {"text": "New text", "saved": "2026-11-01", "updated": "2026-11-05"})

    def test_job_ids_with_colons_and_odd_tokens(self):
        with tempfile.TemporaryDirectory() as d:
            a = descriptions.Archive(Path(d))
            a.update("jsonld:careers.x/y:R:123", "Text", "2026-11-01")
            a.save()
            self.assertEqual(descriptions.Archive(Path(d)).get("jsonld:careers.x/y:R:123"), "Text")
            self.assertTrue((Path(d) / "jsonld" / "careers.x_y.json").exists())

    def test_broken_shard_does_not_stop_the_run(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "lever").mkdir()
            (Path(d) / "lever" / "beta.json").write_text("{not json")
            a = descriptions.Archive(Path(d))
            self.assertEqual(a.get("lever:beta:1"), "")
            self.assertEqual(a.update("lever:beta:1", "Text", "2026-11-01"), "new")

    def test_long_text_is_capped(self):
        self.assertEqual(len(descriptions.normalise("x" * 50000)), descriptions.MAX_CHARS)


class TestDeadline(unittest.TestCase):
    def test_phrases(self):
        cases = {
            "Application deadline: 15 December 2026.": "2026-12-15",
            "Bewerbungsschluss ist der 15.01.2027": "2027-01-15",
            "Apply by January 10th, 2027": "2027-01-10",
            "date limite de candidature : 20 décembre": "2026-12-20",      # no year: next 20 December
            "Please apply before the 5th of January": "2027-01-05",
            "Reageren kan tot uiterlijk 3 januari 2027": "2027-01-03",
            "Deadline 2027-01-31": "2027-01-31",
            "Applications close on 12/15/2026": "2026-12-15",              # US order
        }
        for text, want in cases.items():
            self.assertEqual(parse_deadline(text, REF).date, want, text)

    def test_no_deadline(self):
        for text in ("We have no strict deadline. Start: 1 March 2027", "Deadline-driven environment; start in May",
                     "You work to deadlines.", ""):
            self.assertIsNone(parse_deadline(text, REF).date, text)


class TestViewerEmbed(unittest.TestCase):
    DB = {"generated_at": "2026-11-26T10:00:00+00:00", "jobs": {
        "greenhouse:a:1": {"title": "Open", "company": "Acme", "status": "open", "countries": ["CH"], "url": "https://x/1"},
        "greenhouse:a:2": {"title": "Closed recently", "company": "Acme", "status": "closed", "closed_on": "2026-11-10",
                           "countries": ["CH"], "url": "https://x/2"},
        "lever:b:3": {"title": "Closed long ago", "company": "Beta", "status": "closed", "closed_on": "2026-09-01",
                      "countries": ["NL"], "url": "https://x/3"},
        "lever:b:4": {"title": "Hidden", "company": "Beta", "status": "open", "countries": ["NL"], "url": "https://x/4"},
        "lever:b:5": {"title": "No text", "company": "Beta", "status": "open", "countries": ["NL"], "url": "https://x/5"},
    }}

    def build(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            arch = descriptions.Archive(Path(d) / "descriptions")
            for jid in ("greenhouse:a:1", "greenhouse:a:2", "lever:b:3", "lever:b:4"):
                arch.update(jid, f"Description of {jid} </script><script>alert(1)</script>", "2026-11-01")
            us = Path(d) / "user_state.json"
            us.write_text(json.dumps({"hidden": ["lever:b:4"]}))
            out = Path(d) / "index.html"
            info = viewer.build(self.DB, out, user_state=us, archive=arch, country_names={"CH": "Switzerland"}, **kw)
            return info, out.read_text(encoding="utf-8")

    def test_open_and_recently_closed_only_and_compressed(self):
        info, html = self.build()
        texts = unpack(desc_chunks(html))
        self.assertEqual(sorted(texts), ["greenhouse:a:1", "greenhouse:a:2"])   # not closed in Sept, not hidden, not missing
        self.assertEqual(info["descriptions"], 2)
        self.assertNotIn("Description of", html)                              # stored compressed
        self.assertEqual(html.count("</script>"), 3)
        self.assertEqual(len(desc_chunks(html)), 1)                           # one chunk per feed (lever:b had none)

    def test_deterministic_bytes(self):
        self.assertEqual(self.build()[1], self.build()[1])

    def test_size_cap_drops_closed_descriptions(self):
        info, html = self.build(max_bytes=1)
        self.assertEqual(sorted(unpack(desc_chunks(html))), ["greenhouse:a:1"])

    def test_country_names_for_copy_text(self):
        _, html = self.build()
        self.assertIn('"country_names":{"CH":"Switzerland"}', html)
        self.assertIn("Copy for Claude", html)
        self.assertIn("(Job description not captured; open the link.)", html)


class FakeProvider:
    def __init__(self, postings):
        self.postings = postings

    def fetch(self, client, company):
        return self.postings


class TestPipelineArchive(unittest.TestCase):
    def test_run_saves_descriptions_and_keeps_them_after_close(self):
        def posting(jid, desc):
            return Posting(provider="fake", company="Acme", token="acme", job_id=jid, title="Marketing Intern",
                           url=f"https://x/{jid}", locations=["Zurich, Switzerland"],
                           description=desc)
        companies = [{"name": "Acme", "provider": "fake", "token": "acme"}]
        with tempfile.TemporaryDirectory() as d:
            data, docs = Path(d) / "data", Path(d) / "docs"
            data.mkdir()
            runs = [[posting("1", "Apply by 15 December 2026. Great internship.")], [], []]
            for postings in runs:
                with mock.patch.dict(pipeline.PROVIDERS, {"fake": FakeProvider(postings)}), \
                        mock.patch.object(pipeline, "load_companies", return_value=companies):
                    summary = pipeline.run(data_dir=data, docs_dir=docs)
            db = json.loads((data / "jobs.json").read_text())
            self.assertEqual(db["jobs"]["fake:acme:1"]["status"], "closed")
            self.assertEqual(db["jobs"]["fake:acme:1"]["deadline"], "2026-12-15")
            self.assertNotIn("description", db["jobs"]["fake:acme:1"])          # jobs.json stays small
            shard = json.loads((data / "descriptions" / "fake" / "acme.json").read_text())
            self.assertIn("Great internship", shard["1"]["text"])               # kept after closing
            self.assertIn("descriptions", summary)


if __name__ == "__main__":
    unittest.main()
