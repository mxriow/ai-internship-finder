"""Part B: split strategy/consulting, new commercial/e-commerce/analytics categories, Dutch rules, duration."""
import unittest

from finder.classify import Classifier
from finder.pipeline import load_config

CLF = Classifier(load_config())


def cat(title, desc="", dept=None):
    return CLF.category(title, desc, dept)


class TestNewCategories(unittest.TestCase):
    def check(self, cases):
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(cat(title)[0], expected)

    def test_strategy_vs_consulting(self):
        self.check({
            "Internship: Enterprise Strategy": "strategy", "Strategic Pricing - Product Management Intern": "strategy",
            "Corporate Development Intern": "strategy", "Stage Stratégie": "strategy",
            "Digital Consulting Intern – 6 months": "consulting", "Oliver Wyman - Intern Consultant": "consulting",
            "Strategy Consulting Internship": "consulting", "Deal Advisory Intern": "consulting",
        })

    def test_ecommerce_digital(self):
        self.check({
            "E-Commerce Intern": "ecommerce_digital", "Internship Performance Marketing": "ecommerce_digital",
            "Online Marketing Praktikum": "ecommerce_digital", "Amazon Marketplace Intern": "ecommerce_digital",
            "Shopify Store Intern": "ecommerce_digital", "D2C Growth Intern": "ecommerce_digital",
            "Digital Marketing Internship": "ecommerce_digital", "SEO/SEA Werkstudent": "ecommerce_digital",
        })

    def test_commercial(self):
        self.check({
            "Internship '27: Customer Development - Trade Marketing": "commercial",
            "Internship '27: Field Sales & Trade Marketing": "commercial",
            "Internship '27: Customer Development": "commercial",
            "Customer Development - Category & Account Management": "commercial",
            "Sales Force Effectiveness Intern at Abbott Hoofddorp": "commercial", "SFE/CRM Intern": "commercial",
            "Shopper Marketing Intern": "commercial", "Key Account Management Praktikum": "commercial",
            "Intern Commercial Excellence": "commercial", "Stage Commerciële Ondersteuning": "commercial",
        })

    def test_marketing_analytics(self):
        self.check({
            "Consumer Insights Intern": "marketing_analytics", "Market Research Internship": "marketing_analytics",
            "Marketing Analytics Intern": "marketing_analytics", "Sales Analytics Working Student": "marketing_analytics",
            "Praktikum Marktforschung": "marketing_analytics",
        })

    def test_generic_marketing_and_sales_still_work(self):
        self.check({"Marketing Intern": "marketing", "Brand Management Internship": "brand",
                    "Sales Internship (m/f/d)": "sales", "Tech Sales Internship-Arabic Market": "sales"})


class TestDutchRules(unittest.TestCase):
    def test_dutch_science_compounds_excluded(self):
        for title in ["Stagiair - MBO Microbiologie/Biochemie/Procestechnologie - Tissue Culture",
                      "Stage Chemie Lab", "Afstudeerstage Werktuigbouwkunde", "Stage Biotechnologie"]:
            with self.subTest(title=title):
                self.assertEqual(cat(title)[0], "excluded")

    def test_technische_with_business_goes_to_review(self):
        self.assertTrue(cat("Stage Technische Bedrijfskunde")[1])

    def test_generic_hbo_stage_goes_to_review(self):
        for title in ["HBO/WO Stage: Data Management Verbetering", "HBO Stage: Quality Systems Glossery",
                      "Kom stage lopen bij Abbott Olst vanaf Februari 2027"]:
            with self.subTest(title=title):
                category, review, _ = cat(title)
                self.assertTrue(review, (title, category))


class TestDuration(unittest.TestCase):
    def test_benefit_is_not_duration(self):
        text = ("Flexible Arbeitszeiten und die Möglichkeit für Telearbeit (Remote) für bis zu 8 Wochen pro Jahr. "
                "Kostenloser Zugriff auf das beste TV.")
        self.assertIsNone(CLF.duration(text))

    def test_other_non_durations(self):
        for text in ["You have 2 months of experience with Excel.", "Notice period of 3 months applies.",
                     "We offer 25 days vacation and 6 weeks per year of remote work."]:
            with self.subTest(text=text):
                self.assertIsNone(CLF.duration(text))

    def test_real_durations(self):
        cases = {"This is a 6-month internship starting in February.": "6-month",
                 "Dauer: 6-12 Monate, ab sofort": "6-12 Monate",
                 "Stage de 6 mois à Luxembourg": "6 mois",
                 "Een stage van 5 maanden in Amsterdam": "5 maanden",
                 "Minimum duration: at least 6 months": "6 months"}
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(CLF.duration(text), expected)


if __name__ == "__main__":
    unittest.main()
