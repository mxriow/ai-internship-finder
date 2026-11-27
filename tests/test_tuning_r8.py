"""Round-8 rule fixes: known misclassifications, hiring-process durations, stale start dates."""
import unittest
from datetime import date

from finder.classify import Classifier
from finder.dates import is_past, parse_start
from finder.models import Posting
from finder.pipeline import load_config

CLF = Classifier(load_config())
REF = date(2026, 11, 4)


class TestKnownBugs(unittest.TestCase):
    def test_categories(self):
        for title, want in [
            ("Internship – AI Engineer - AI-Powered CRM – Data Extraction & KYC Support", "excluded"),   # Lombard Odier
            ("Transfer Pricing Intern – January 2027", "finance"),                                     # PwC
            ("Praktikant Verrechnungspreise / Transfer Pricing (w/m/d)", "finance"),
            ("Praktikant für das Pricing Aktuariat (m/w/d)", "finance"),
            ("Finance (Pricing) Intern", "finance"),
            ("Pricing Analyst Intern", "marketing_analytics"),
            ("Stage Sea Logistics", "operations_supply_chain"),                                        # not SEA ads
            ("SEA & SEO Marketing Intern", "ecommerce_digital"),
            ("Mandatory Internship in Strategic Purchasing of Logistic Transport Services", "operations_supply_chain"),
            ("Strategic Finance Internship", "finance"),
            ("Strategic Pricing - Product Management Intern", "strategy"),
            ("Talent Acquisition & Employer Branding Intern", "hr"),
            ("Internship HR Retail", "hr"),
            ("Brand Manager Intern", "brand"),
            ("CRM Marketing Intern", "marketing"),
        ]:
            with self.subTest(title=title):
                self.assertEqual(CLF.category(title)[0], want)

    def test_givaudan_product_development_not_marketing(self):
        cat = CLF.category("Dairy Product Development Intern (m/f/d)", "", "Sales, Marketing, Communications")[0]
        self.assertEqual(cat, "excluded")

    def test_msd_north_wales_pennsylvania_is_not_uk(self):
        self.assertEqual(CLF.location(["USA - Pennsylvania - North Wales (Upper Gwynedd)", "United States of America"])[0], [])
        self.assertEqual(CLF.location(["Bangor, North Wales, United Kingdom"])[0], ["UK"])
        self.assertEqual(CLF.location(["Cardiff, Wales"])[0], ["UK"])
        # MSD's Workday UK country filter returns this posting; the listed locations win
        self.assertEqual(CLF.location(["USA - Pennsylvania - North Wales (Upper Gwynedd)", "United States of America"], ["UK"])[0], [])
        self.assertEqual(CLF.location(["3 Locations"], ["UK"])[0], ["UK"])          # Workday summary: trust the facet
        self.assertEqual(CLF.location(["London", "New York, USA"], ["UK"])[0], ["UK"])

    def test_hiring_process_weeks_are_not_a_duration(self):
        text = ("we'll invite you to complete an online assessment though Talogytech– usually in 1- 2 weeks "
                "from your applications' date.")
        self.assertIsNone(CLF.duration(text))
        self.assertEqual(CLF.duration("a 6-month internship"), "6-month")


class TestStartDates(unittest.TestCase):
    def check(self, title, desc, month, asap=False):
        r = parse_start(title, desc, REF)
        self.assertEqual((r.month, r.asap), (month, asap), r.label)

    def test_languages(self):
        self.check("Intern", "We are looking for interns starting January 2027.", "2027-01")
        self.check("Praktikum", "Das Praktikum beginnt ab Februar 2027.", "2027-02")
        self.check("Stage", "Stage de 6 mois dès janvier.", "2027-01")          # no year: next January
        self.check("Stage", "De stage start per februari.", "2027-02")
        self.check("Intern", "Start: 01.04.2027", "2027-04")
        self.check("Intern", "Startdatum: 1 maart 2027", "2027-03")
        self.check("Intern", "Le stage débutera à partir de mars 2027.", "2027-03")
        self.check("Intern", "Beginn: zum 01.03.2027 oder nach Vereinbarung", "2027-03")
        self.check("Intern", "The internship starts in Q2 2027.", "2027-04")
        self.check("Praktikant", "Start Frühjahr 2027, 6 Monate", "2027-03")
        self.check("Intern", "You will start from March to August 2027.", "2027-03")

    def test_titles_and_seasons(self):
        self.check("Summer Internship 2027", "", "2027-06")
        self.check("Intern", "Internship for summer 2027 in Zurich.", "2027-06")
        self.check("Transfer Pricing Intern – January 2027", "", "2027-01")
        self.check("Kom stage lopen bij Abbott Olst vanaf Februari 2027", "", "2027-02")
        self.check("Internship – AI & Data – as of February 2027", "", "2027-02")

    def test_asap_and_noise(self):
        self.check("Werkstudent", "Eintritt ab sofort möglich.", None, True)
        self.check("Intern", "Starting as soon as possible, for 6 months", None, True)
        self.check("Intern", "We offer 25 days of holidays per year and a salary from CHF 2000.", None)
        self.check("Praktikum in Support, Abwicklung & Standortthemen", "Themen wie Abfall und Entsorgung.", None)
        self.check("Werkstudent Administration", "Wintersemesterferien 2026 im Werk", None)
        self.check("Engineer, New Grad (2027 Start)", "You will graduate between fall 2026 and summer 2027 with a degree.", None)
        self.check("Intern", "Founded in 2010, we have offices from Zurich to Dubai since May 2015.", None)
        self.check("Intern", "Please apply by 15.12.2026. The internship starts on 1 April 2027.", "2027-04")

    def test_stale(self):
        self.assertTrue(is_past("2026-08", REF))
        self.assertFalse(is_past("2026-11", REF))
        self.assertFalse(is_past(None, REF))
        p = Posting(provider="x", company="X", token="x", job_id="1", title="Marketing Intern", url="u",
                    locations=["Zurich"], description="Start date: August 2026. Apply now.")
        res = CLF.classify(p)
        self.assertEqual(res.start_month, "2026-08")
        self.assertTrue(res.stale)
        p.description = "Start date: October."          # no year: the next October, never stale
        self.assertFalse(CLF.classify(p).stale)


class TestViewerTitle(unittest.TestCase):
    def test_heading_lists_all_target_countries(self):
        import tempfile
        from pathlib import Path
        from finder import viewer
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "index.html"
            viewer.build({"jobs": {}}, out, countries=["CH", "NL", "LU", "AE", "BE", "DE", "UK"])
            html = out.read_text(encoding="utf-8")
        self.assertIn("Business internships · CH NL LU AE BE DE UK</h1>", html)
        self.assertNotIn("__COUNTRIES__", html)
