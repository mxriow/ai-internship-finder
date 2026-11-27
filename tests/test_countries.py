"""NL / LU / AE location rules, look-alikes, and Dutch internship terms."""
import unittest

from finder.classify import Classifier
from finder.models import Posting
from finder.pipeline import load_config

CLF = Classifier(load_config())


def loc(*locations, codes=None):
    return CLF.location(list(locations), codes)


class TestNetherlands(unittest.TestCase):
    def test_cities(self):
        cases = {
            "Amsterdam, Netherlands": "Amsterdam", "Amstelveen": "Amstelveen", "Rotterdam": "Rotterdam",
            "Utrecht, NL": "Utrecht", "Den Haag": "The Hague", "The Hague, Netherlands": "The Hague",
            "Eindhoven": "Eindhoven", "Hoofddorp, Noord-Holland": "Hoofddorp", "Schiphol-Rijk": "Schiphol",
            "Haarlem": "Haarlem", "Leiden": "Leiden", "Nijmegen": "Nijmegen", "Groningen": "Groningen",
            "Maastricht": "Maastricht", "Breda": "Breda", "Zwolle": "Zwolle", "Amsterdam-Zuidoost": "Amsterdam",
        }
        for text, city in cases.items():
            with self.subTest(text=text):
                codes, cities = loc(text)
                self.assertEqual(codes, ["NL"])
                self.assertIn(city, cities)

    def test_country_names_and_codes(self):
        for text in ["Netherlands", "Nederland", "Remote - Netherlands", "Office, NL", "Office (NLD)"]:
            with self.subTest(text=text):
                self.assertEqual(loc(text)[0], ["NL"])
        self.assertEqual(loc("Office", codes=["nl"])[0], ["NL"])

    def test_look_alikes(self):
        for text in ["Amsterdam, NY", "Amsterdam, New York, United States", "Rotterdam, NY",
                     "Rotterdam, New York", "Holland, MI", "Holland, Michigan", "New Amsterdam"]:
            with self.subTest(text=text):
                self.assertEqual(loc(text)[0], [])


class TestLuxembourg(unittest.TestCase):
    def test_cities(self):
        cases = {
            "Luxembourg": "Luxembourg", "Luxembourg City, Luxembourg": "Luxembourg", "Kirchberg, Luxembourg": "Luxembourg",
            "Esch-sur-Alzette": "Esch-sur-Alzette", "Belval": "Esch-sur-Alzette", "Strassen": "Strassen",
            "Bertrange, Luxembourg": "Bertrange", "Leudelange": "Leudelange", "Contern": "Contern",
        }
        for text, city in cases.items():
            with self.subTest(text=text):
                codes, cities = loc(text)
                self.assertEqual(codes, ["LU"])
                self.assertIn(city, cities)

    def test_country_names_and_codes(self):
        for text in ["Grand Duchy of Luxembourg", "Luxemburg", "Office, LUX"]:
            with self.subTest(text=text):
                self.assertEqual(loc(text)[0], ["LU"])
        self.assertEqual(loc("Office", codes=["LU"])[0], ["LU"])

    def test_belgian_province_and_other_look_alikes(self):
        for text in ["Arlon", "Arlon, Belgium", "Bastogne", "Bastogne, Luxembourg, Belgium", "Marche-en-Famenne",
                     "Province de Luxembourg", "Province of Luxembourg, Belgium", "Luxembourg, Belgium",
                     "Kirchberg SG", "Kirchberg, Switzerland", "Kirchberg an der Pielach, Austria",
                     "Jardin du Luxembourg, Paris"]:
            with self.subTest(text=text):
                self.assertNotIn("LU", loc(text)[0])

    def test_lucerne_canton_code_is_not_luxembourg(self):
        self.assertEqual(loc("Kriens, LU")[0], ["CH"])
        self.assertEqual(loc("Root, LU")[0], [])     # unknown Swiss village: no false Luxembourg either


class TestUAE(unittest.TestCase):
    def test_cities(self):
        cases = {
            "Dubai, United Arab Emirates": "Dubai", "DIFC": "Dubai", "Dubai Silicon Oasis": "Dubai",
            "Jebel Ali": "Dubai", "Business Bay, Dubai": "Dubai", "Dubai Media City": "Dubai",
            "Abu Dhabi": "Abu Dhabi", "ADGM": "Abu Dhabi", "Masdar City": "Abu Dhabi", "Sharjah": "Sharjah",
            "Ajman": "Ajman",
        }
        for text, city in cases.items():
            with self.subTest(text=text):
                codes, cities = loc(text)
                self.assertEqual(codes, ["AE"])
                self.assertIn(city, cities)

    def test_country_names_and_codes(self):
        for text in ["United Arab Emirates", "UAE", "Remote - UAE", "Office, AE", "U.A.E."]:
            with self.subTest(text=text):
                self.assertEqual(loc(text)[0], ["AE"])
        self.assertEqual(loc("Office", codes=["ae"])[0], ["AE"])

    def test_region_in_title_only_does_not_count(self):
        p = Posting(provider="x", company="X", token="x", job_id="1", url="u",
                    title="Marketing Intern - MEA region (Dubai, Abu Dhabi)", locations=["London, United Kingdom"])
        self.assertNotIn("AE", CLF.classify(p).countries)      # London itself is now a UK match
        for text in ["MEA", "Middle East", "EMEA", "GCC", "Dubai, TX"]:
            with self.subTest(text=text):
                self.assertEqual(loc(text)[0], [])


class TestMultiCountry(unittest.TestCase):
    def test_posting_in_several_target_countries(self):
        codes, cities = loc("Zurich, Switzerland", "Amsterdam, Netherlands", "Dubai, UAE")
        self.assertEqual(codes, ["CH", "NL", "AE"])
        self.assertEqual(cities, ["Zurich", "Amsterdam", "Dubai"])


class TestDutchInternships(unittest.TestCase):
    def test_dutch_titles(self):
        cases = {
            "Stagiair Marketing": "intern", "Stagiaire Communicatie (m/v/x)": "intern",
            "Afstudeerstage Business Analytics": "intern", "Meewerkstage Sales": "intern",
            "Stage Marketing & Communicatie": "intern", "Stageplaats Brand Management": "intern",
            "Werkstudent Marketing": "working_student", "Traineeship Commercial 2027": "trainee",
            "Commercieel Traineeship": "trainee",
            # Luxembourg: French and German terms
            "Stage - Fund Administration (6 mois)": "intern", "Stagiaire Audit": "intern",
            "Praktikum Marketing Luxemburg": "intern",
        }
        for title, kind in cases.items():
            with self.subTest(title=title):
                self.assertEqual(CLF.intern_type(title), kind)

    def test_dutch_false_positives(self):
        for title in ["Stage Manager", "Stage Manager - Theater Amsterdam", "Stagebegeleider Zorg",
                      "Stagecoördinator", "International Marketing Manager", "Internal Auditor"]:
            with self.subTest(title=title):
                self.assertIsNone(CLF.intern_type(title))

    def test_dutch_categories(self):
        self.assertEqual(CLF.category("Stagiair Verkoop")[0], "sales")
        self.assertEqual(CLF.category("Stage Communicatie")[0], "communications_pr")
        self.assertEqual(CLF.category("Stage Fund Administration")[0], "finance")

    def test_dutch_language(self):
        nl = ("Wij zoeken een stagiair voor ons team. Jij werkt mee aan onze campagnes en bent ook "
              "betrokken bij het opzetten van nieuwe projecten. Je krijgt een vergoeding.")
        self.assertEqual(CLF.language("Stagiair Marketing", nl), "NL")
        fr = ("Nous recherchons un stagiaire pour notre équipe de Luxembourg. Vous travaillerez avec les équipes "
              "de gestion de fonds et vous participerez à des projets dans un environnement international.")
        self.assertEqual(CLF.language("Stagiaire", fr), "FR")
        self.assertEqual(CLF.language("Stagiair Marketing (m/v/x)", ""), "NL")


if __name__ == "__main__":
    unittest.main()
