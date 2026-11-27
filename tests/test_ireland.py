"""Ireland (IE): cities, look-alikes in the US/London, and Northern Ireland staying UK."""
import unittest

from finder.classify import Classifier
from finder.pipeline import load_config

CLF = Classifier(load_config())
loc = lambda *l, codes=None: CLF.location(list(l), codes)[0]  # noqa: E731


class TestIreland(unittest.TestCase):
    def test_requested_cases(self):
        self.assertEqual(loc("Dublin, Ireland"), ["IE"])
        self.assertEqual(loc("Dublin 2, Co. Dublin"), ["IE"])
        self.assertEqual(loc("Dublin, OH"), [])
        self.assertEqual(loc("Dublin, California, United States"), [])
        self.assertEqual(loc("Belfast"), ["UK"])
        self.assertEqual(loc("Cork, IE"), ["IE"])

    def test_more_places(self):
        for l in ["Dún Laoghaire", "Sandyford, Dublin 18", "Grand Canal Dock", "Galway", "Limerick", "Athlone",
                  "Naas, Co. Kildare", "Shannon, Co. Clare", "Republic of Ireland", "Remote - Ireland", "Éire"]:
            with self.subTest(l=l):
                self.assertEqual(loc(l), ["IE"])
        self.assertEqual(loc("Anywhere", codes=["IRL"]), ["IE"])
        self.assertEqual(CLF.location(["Dublin 4, Ireland"])[1], ["Dublin"])

    def test_look_alikes_and_northern_ireland(self):
        for l in ["Dublin, Ohio, USA", "Dublin, GA", "Cork Street, London", "Galway, NY", "Limerick, PA",
                  "Waterford, MI", "Waterford, CT"]:
            with self.subTest(l=l):
                self.assertNotIn("IE", loc(l))
        for l in ["Belfast, Northern Ireland", "Derry, Northern Ireland, United Kingdom", "Northern Ireland"]:
            with self.subTest(l=l):
                self.assertEqual(loc(l), ["UK"])


if __name__ == "__main__":
    unittest.main()
