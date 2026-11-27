"""Graduate programmes and the employment-type regression (Redalpine, Oct 2026)."""
import unittest

from finder.classify import Classifier
from finder.pipeline import load_config

CLF = Classifier(load_config())


class TestRedalpineRegression(unittest.TestCase):
    def test_early_stage_title_with_intern_job_type_is_internship(self):
        # Real posting: Personio job type "intern entry-level full-time"; the title's "early stage"
        # used to cancel the match before the job-type field was looked at.
        self.assertEqual(CLF.intern_type("visiting analyst - early stage investments (f/m/d)",
                                         "intern entry-level full-time"), "intern")

    def test_guards_still_work_on_titles(self):
        self.assertIsNone(CLF.intern_type("Account Executive, Early-Stage Startups", "Full-time"))
        self.assertIsNone(CLF.intern_type("Stage Manager", None))
        self.assertIsNone(CLF.intern_type("International Sales Manager", "Full-time"))


class TestUKPlacements(unittest.TestCase):
    def test_placements_are_internships(self):
        for title in ["Biology - Industrial Placement (12 Months)", "Marketing Placement Year 2027/28",
                      "Unilever Industrial Placement Programme - Communications and Corporate Affairs UK",
                      "Finance Placement Student", "Summer Placement - Sales"]:
            with self.subTest(title=title):
                self.assertEqual(CLF.intern_type(title), "intern")

    def test_other_placements_are_not(self):
        for title in ["Placement Consultant", "Senior Placement Coordinator", "Product Placement Manager"]:
            with self.subTest(title=title):
                self.assertIsNone(CLF.intern_type(title))


class TestGraduate(unittest.TestCase):
    def test_graduate_programmes(self):
        for title in ["Swiss Graduate Programme 2027_Private Bank (BLIS)", "Power+ Graduate Program (f/m/d)",
                      "Marketing Assistant - Young Professional Program",
                      "Taste The Future Early Career (Sales & Marketing)- Breda - Netherlands",
                      "Graduate Trader", "Tech Young Professional",
                      "Associate Analyst, Business Administration- Launch Program 2027 - Dubai, UAE",
                      "AI Builder, Emerging Talent Program - EMEA"]:
            with self.subTest(title=title):
                self.assertEqual(CLF.intern_type(title), "graduate")

    def test_internship_wins_over_graduate(self):
        self.assertEqual(CLF.intern_type("Graduate Internship - Marketing"), "intern")
        self.assertEqual(CLF.intern_type("Graduate Trainee Programme"), "trainee")

    def test_not_graduate(self):
        for title in ["Recruiting Coordinator - Campus/Early Careers - Amsterdam", "Early Careers Recruiter",
                      "Head of Graduate Recruitment", "Postgraduate Research Fellow"]:
            with self.subTest(title=title):
                self.assertIsNone(CLF.intern_type(title))


if __name__ == "__main__":
    unittest.main()
