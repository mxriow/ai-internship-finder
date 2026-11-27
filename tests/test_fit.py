"""Best-fit score (finder/fit.py)."""
import unittest

from finder import fit
from finder.pipeline import load_config

CFG = load_config()
S = lambda **j: fit.score(j, CFG["fit_score"], CFG["early_start_before"])  # noqa: E731
BEST = dict(degree="bachelor_ok", language="EN", lang_required=["EN"], category="brand", start_month="2027-05", duration="6 months")


class TestFit(unittest.TestCase):
    def test_best_is_100(self):
        self.assertEqual(S(**BEST), 100)

    def test_each_preference_orders_as_asked(self):
        def ordered(field, values):
            scores = [S(**{**BEST, **v}) for v in values]
            self.assertEqual(scores, sorted(scores, reverse=True), field)
            self.assertGreater(scores[0], scores[-1], field)
        ordered("degree", [{"degree": "bachelor_ok"}, {"degree": "unclear"}, {"degree": "master_required"}])
        ordered("language", [{"lang_required": []}, {"lang_required": ["EN", "DE"]}, {"lang_required": ["FR"]}])
        ordered("category", [{"category": "marketing"}, {"category": "sales"}, {"category": "finance"}])
        ordered("start", [{"start_month": None}, {"start_month": "2027-02"}])
        ordered("duration", [{"duration": "3-6 months"}, {"duration": "12 months"}])

    def test_details(self):
        self.assertEqual(S(**{**BEST, "start_month": "2027-04"}), 100)          # April itself is fine
        self.assertEqual(S(**{**BEST, "start_month": None, "start_asap": True}), 85)
        self.assertEqual(S(**{**BEST, "language": "DE", "lang_required": []}), 85)   # a German posting needs German
        self.assertEqual(fit.duration_months("4-6 Monate"), 6)
        self.assertEqual(fit.duration_months("15 week"), 3.5)
        self.assertIsNone(fit.duration_months(None))
        self.assertEqual(S(**{**BEST, "category": "excluded"}), 75)


if __name__ == "__main__":
    unittest.main()
