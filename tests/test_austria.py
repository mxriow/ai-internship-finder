"""Austria (AT): cities, country names, and same-named places elsewhere."""
import unittest

from finder.classify import Classifier
from finder.pipeline import load_config

CLF = Classifier(load_config())
loc = lambda *l, codes=None: CLF.location(list(l), codes)[0]  # noqa: E731


class TestAustria(unittest.TestCase):
    def test_cities_and_names(self):
        for l in ["Vienna", "Wien", "1010 Wien", "Vienna, Austria", "Graz", "Linz, Upper Austria", "Salzburg", "Innsbruck",
                  "Klagenfurt am Wörthersee", "Dornbirn", "Wattens", "Fuschl am See", "Wiener Neudorf", "Vösendorf",
                  "Austria", "Österreich", "Remote - Austria", "St. Pölten"]:
            with self.subTest(l=l):
                self.assertEqual(loc(l), ["AT"])
        self.assertEqual(loc("Somewhere", codes=["AT"]), ["AT"])
        self.assertEqual(CLF.location(["1030 Wien"])[1], ["Wien"])

    def test_look_alikes(self):
        for l in ["Vienna, Virginia", "Vienna, VA", "Vienna, VA, United States", "Tysons Corner, Vienna, Virginia",
                  "Vienna, WV", "Vienna, Ohio", "Linz am Rhein", "Linz, Rheinland-Pfalz, Germany", "Salzburg, Romania",
                  "Ocna Sibiului (Salzburg)"]:
            with self.subTest(l=l):
                self.assertNotIn("AT", loc(l))

    def test_other_countries_unaffected(self):
        self.assertEqual(loc("Zürich"), ["CH"])
        self.assertEqual(loc("Munich, Germany"), ["DE"])
        self.assertEqual(loc("Kirchberg, Luxembourg"), ["LU"])


if __name__ == "__main__":
    unittest.main()
