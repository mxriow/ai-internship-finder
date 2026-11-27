"""Degree and language requirements. The first three cases quote real postings (Oct 2026)."""
import unittest

from finder.pipeline import load_config
from finder.requirements import RequirementExtractor

RX = RequirementExtractor(load_config())

ABBOTT_MARKETING = ("Your profile: Currently enrolled in or recently graduated from a leading MBA program or a "
                    "Master's degree program. Fluent English language skills, both written and spoken.")
AMGEN_ONCOLOGY = ("The individual we seek is a proactive student or recent graduate with these qualifications:\n"
                  "Ongoing or completed studies in Pharmacy, Life Sciences, Medicine, Business Administration or a "
                  "related field\nFluent in German and proficient in English (written and spoken), French is a plus")
HITACHI_PM_MARKETING = ("The internship lasts 6 months, with the possibility to align your Master’s thesis with relevant "
                        "company projects.\nCurrently enrolled in a master’s program in management, technology, "
                        "economics, engineering, or a related field\nExcellent communication skills in English;\n"
                        "German is a plus")


class TestRealPostings(unittest.TestCase):
    def test_abbott_intern_marketing_requires_master_or_mba(self):
        r = RX.extract(ABBOTT_MARKETING)
        self.assertEqual(r.degree, "master_required")
        self.assertEqual((r.lang_required, r.lang_plus), (["EN"], []))

    def test_amgen_marketing_oncology_requires_fluent_german(self):
        r = RX.extract(AMGEN_ONCOLOGY)
        self.assertIn("DE", r.lang_required)
        self.assertEqual((r.lang_required, r.lang_plus), (["DE", "EN"], ["FR"]))
        self.assertEqual(r.degree, "unclear")

    def test_hitachi_pm_marketing_master_german_plus(self):
        r = RX.extract(HITACHI_PM_MARKETING)
        self.assertEqual(r.degree, "master_required")
        self.assertEqual((r.lang_required, r.lang_plus), (["EN"], ["DE"]))


class TestDegree(unittest.TestCase):
    def test_cases(self):
        cases = {
            "You are a Bachelor or Master student in Business Administration.": "bachelor_ok",
            "Enrolled in a bachelor's or master's programme in marketing.": "bachelor_ok",
            "You have completed your Bachelor's degree and are enrolled in a Master's program.": "master_required",
            "Abgeschlossenes Bachelorstudium und eingeschrieben im Masterstudium.": "master_required",
            "Sie sind Bachelorstudent*in der Betriebswirtschaft.": "bachelor_ok",
            "Student (HBO/WO) Commerciële Economie of Bedrijfskunde.": "bachelor_ok",
            "Étudiant(e) en Master 2 en finance (Bac+5).": "master_required",
            "Undergraduate students in their penultimate year.": "bachelor_ok",
            "Bachelor's degree completed; a Master's degree is a plus.": "bachelor_ok",
            "A master's degree is an advantage. You are a motivated student.": "unclear",
            "You are passionate about marketing and data.": "unclear",
            "Responsible for global master data quality.": "unclear",        # 'master data' is not a degree
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(RX.degree(text)[0], expected)

    def test_note_is_the_deciding_sentence(self):
        deg, note = RX.degree(ABBOTT_MARKETING)
        self.assertIn("MBA", note)


class TestLanguages(unittest.TestCase):
    def test_cases(self):
        cases = {
            "Fluent in English, German is a plus.": (["EN"], ["DE"]),
            "Verhandlungssichere Deutsch- und Englischkenntnisse": (["DE", "EN"], []),
            "Sehr gute Deutschkenntnisse, Französisch von Vorteil": (["DE"], ["FR"]),
            "Maîtrise du français et de l'anglais; l'allemand est un atout.": (["EN", "FR"], ["DE"]),
            "Je spreekt vloeiend Nederlands en Engels.": (["EN", "NL"], []),
            "Kennis van het Duits is een pré.": ([], ["DE"]),
            "English: fluent. German: nice to have.": (["EN"], ["DE"]),
            "Arabic is a plus; excellent English required.": (["EN"], ["AR"]),
            "Please send your application in English or German.": ([], []),
            "You will work with Deutsche Bank teams in the German-speaking part of Switzerland.": ([], []),
            "Fluent German is a plus.": ([], ["DE"]),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(RX.languages(text), expected)


if __name__ == "__main__":
    unittest.main()
