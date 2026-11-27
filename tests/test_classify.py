import unittest
from pathlib import Path

import yaml

from finder.classify import Classifier
from finder.models import Posting, html_to_text
from finder.pipeline import load_config

FIX = Path(__file__).parent / "fixtures"
CLF = Classifier(load_config())


class TestIntern(unittest.TestCase):
    fx = yaml.safe_load((FIX / "titles.yaml").read_text(encoding="utf-8"))

    def test_internship_titles(self):
        for title, kind in self.fx["intern"]:
            with self.subTest(title=title):
                self.assertEqual(CLF.intern_type(title), kind)

    def test_false_positives(self):
        for title in self.fx["not_intern"]:
            with self.subTest(title=title):
                self.assertIsNone(CLF.intern_type(title))

    def test_required_false_positives(self):
        self.assertIsNone(CLF.intern_type("International Sales Manager"))
        self.assertIsNone(CLF.intern_type("Internal Communications Manager"))

    def test_employment_type_field(self):
        self.assertEqual(CLF.intern_type("Marketing Assistant", "Internship"), "intern")
        self.assertEqual(CLF.intern_type("Marketing Assistant", "Intern"), "intern")
        self.assertIsNone(CLF.intern_type("Marketing Assistant", "Full-time"))
        self.assertIsNone(CLF.intern_type("Marketing Assistant", "International"))


class TestLocation(unittest.TestCase):
    def loc(self, locations, codes=None):
        return CLF.location(locations, codes)

    def test_swiss_cities(self):
        cases = {
            "Zürich, Switzerland": "Zurich", "Zurich": "Zurich", "Geneva": "Geneva", "Genève": "Geneva",
            "Basel, BS": "Basel", "Bern": "Bern", "Lausanne, Vaud": "Lausanne", "Zug": "Zug",
            "Lugano (TI)": "Lugano", "Luzern": "Lucerne", "Winterthur": "Winterthur",
            "St. Gallen": "St. Gallen", "Vevey": "Vaud Riviera", "Le Brassus": "Jura arc / watch valley",
            "Baden, Aargau": "Baden", "Baden-Daettwil, Aargau, Switzerland": "Baden-Daettwil", "Kaiseraugst": "Basel", "Rotkreuz": "Zug",
        }
        for text, city in cases.items():
            with self.subTest(text=text):
                codes, cities = self.loc([text])
                self.assertEqual(codes, ["CH"])
                self.assertIn(city, cities)

    def test_country_names_and_codes(self):
        self.assertEqual(self.loc(["Remote - Switzerland"])[0], ["CH"])
        self.assertEqual(self.loc(["Schweiz"])[0], ["CH"])
        self.assertEqual(self.loc(["Suisse romande"])[0], ["CH"])
        self.assertEqual(self.loc(["Office"], ["ch"])[0], ["CH"])
        self.assertEqual(self.loc(["Nyon, VD, CH"])[0], ["CH"])

    def test_multi_location(self):
        self.assertEqual(self.loc(["London, UK", "Paris, France", "Zurich, Switzerland"])[0], ["CH", "UK"])

    def test_not_swiss(self):
        for text in ["Remote", "Remote - Europe", "London, United Kingdom", "Baden-Baden, Germany",
                     "Baden-Württemberg", "Geneva, IL", "Bern, NC", "Munich", "Chicago, IL",
                     "Zugspitze resort", "Berner Street, London", "Basildon", "Lucerne, CA",
                     "Lake Zurich, Illinois, United States", "Zurich, IL"]:
            with self.subTest(text=text):
                self.assertNotIn("CH", self.loc([text])[0])
        self.assertNotIn("CH", self.loc(["Office"], ["DE"])[0])


class TestCategory(unittest.TestCase):
    def cat(self, title, desc="", dept=None):
        return CLF.category(title, desc, dept)

    def test_title_categories(self):
        cases = {
            "Marketing Intern": "marketing", "Brand Management Intern": "brand",
            "Brand Marketing Internship": "brand", "Praktikum Vertrieb": "sales",
            "Sales Excellence Intern": "commercial", "Business Development Intern": "business_development",
            "Strategy & Transformation Intern": "strategy",
            "Praktikum Unternehmensberatung": "consulting",
            "Corporate Communications Intern": "communications_pr",
            "Praktikum Unternehmenskommunikation": "communications_pr",
            "Stage Communication (H/F)": "communications_pr",
            "Supply Chain Intern": "operations_supply_chain", "Procurement Intern": "operations_supply_chain",
            "Intern Controlling": "finance", "Summer Analyst - Investment Banking": "finance",
            "HR Intern - Talent Acquisition": "hr", "Praktikum Personalmanagement": "hr",
            "Intern Sustainability": "other_business", "Praktikum KV": "other_business",
            "Tirocinio Marketing": "marketing", "Stagista Vendite": "sales",
            "Intern Operations & Supply Chain - Future Talent Program": "operations_supply_chain",
            "Client Services Intern": "sales", "Intern Global Direct-to-Consumer (D2C) - 6 months": "ecommerce_digital",
            "Internship: Data Analytics Intern - Product Control 100%": "finance",
            "Project Support Intern - Global Citizenship": "other_business",
            "Visual Merchandising Intern": "marketing", "Retail Operations Intern": "sales",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                cat, review, _ = self.cat(title)
                self.assertEqual(cat, expected)
                self.assertFalse(review)

    def test_excluded(self):
        for title in ["Software Engineering Intern", "Data Science Intern", "Praktikum Labor Analytik",
                      "Intern Clinical Operations Research Scientist", "Legal Intern", "Praktikum Rechtsabteilung",
                      "IT Support Intern", "Praktikant Informatik", "Machine Learning Intern",
                      "Lernende/r Kauffrau/Kaufmann EFZ", "Intern - Cyber Security",
                      "Praktikum Betriebsengineering für 6-12 Monate (m/w/d)",
                      "Praktikant Gerätequalifizierung QC 80-100% (m/w/d)",
                      "Universitätspraktikant:in im Bereich Spurenanalytik",
                      "Internship in tDMPK-PD Drug Disposition and Bioanalysis",
                      "Disney Research Studio Intern", "Image and Data Processing Libraries Intern"]:
            with self.subTest(title=title):
                self.assertEqual(self.cat(title)[0], "excluded")

    def test_borderline_goes_to_review(self):
        cat, review, reason = self.cat("Sales Engineer Intern")
        self.assertEqual(cat, "sales")
        self.assertTrue(review)
        cat, review, _ = self.cat("Internship (6 months)",
                                  "Support our marketing team with campaigns, digital marketing analytics "
                                  "and social media content for our marketing plan.")
        self.assertEqual(cat, "marketing")
        self.assertTrue(review)
        cat, review, _ = self.cat("Intern", "")
        self.assertEqual(cat, "other_business")
        self.assertTrue(review)

    def test_weak_marketing_words_do_not_match(self):
        cat, _, _ = self.cat("Internship: Digital & OE Support for Performance Excellence")
        self.assertNotEqual(cat, "marketing")

    def test_technical_description_excluded(self):
        cat, review, _ = self.cat("Summer Intern 2027", "You will write CUDA kernels and C++ software, "
                                  "work with our engineering team on machine learning and cloud infrastructure.")
        self.assertEqual((cat, review), ("excluded", True))

    def test_business_role_in_science_division_goes_to_review(self):
        self.assertEqual(self.cat("Intern HR Biologics 80-100%")[:2], ("hr", True))

    def test_department_fallback(self):
        cat, review, _ = self.cat("Internship 2027", dept="Global Marketing")
        self.assertEqual((cat, review), ("marketing", True))


class TestLanguage(unittest.TestCase):
    def test_languages(self):
        self.assertEqual(CLF.language("Praktikum", "Wir suchen dich für unser Team. Du bist motiviert und die "
                                      "Arbeit mit uns ist für dich eine Chance, mit der du wächst."), "DE")
        self.assertEqual(CLF.language("Stage", "Nous recherchons pour notre équipe une personne motivée. Vous "
                                      "travaillerez avec les équipes dans un environnement des plus stimulants."), "FR")
        self.assertEqual(CLF.language("Intern", "You will join our team and work with the brand. We are looking "
                                      "for interns who have drive and are ready for the challenge."), "EN")
        self.assertEqual(CLF.language("Tirocinio Marketing", ""), "IT")
        self.assertEqual(CLF.language("Marketing Intern", "", declared="en"), "EN")


class TestEndToEnd(unittest.TestCase):
    def test_classify_posting(self):
        p = Posting(provider="lever", company="Acme", token="acme", job_id="1",
                    title="Marketing Internship (6 months)", url="https://x",
                    locations=["Zurich, Switzerland", "London"], description=html_to_text(
                        "<p>Start date: September 2027. Duration: 6 months.</p><p>You will join our team.</p>"))
        r = CLF.classify(p)
        self.assertEqual((r.intern_type, r.countries, r.category), ("intern", ["CH", "UK"], "marketing"))
        self.assertEqual(r.cities, ["Zurich", "London"])
        self.assertIn("6 months", r.duration)
        self.assertIn("September 2027", r.start)

    def test_html_to_text_double_escaped(self):
        self.assertEqual(html_to_text("&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;"), "Hello & welcome")


if __name__ == "__main__":
    unittest.main()
