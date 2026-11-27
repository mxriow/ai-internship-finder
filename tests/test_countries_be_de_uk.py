"""Belgium, Germany, United Kingdom: cities, codes and look-alikes."""
import unittest

from finder.classify import Classifier
from finder.models import Posting
from finder.pipeline import load_config

CLF = Classifier(load_config())


def loc(*locations, codes=None):
    return CLF.location(list(locations), codes)


class TestBelgium(unittest.TestCase):
    def test_cities(self):
        cases = {"Brussels, Belgium": "Brussels", "Bruxelles": "Brussels", "Brussel": "Brussels",
                 "Antwerp": "Antwerp", "Antwerpen": "Antwerp", "Ghent": "Ghent", "Gent": "Ghent",
                 "Leuven": "Leuven", "Mechelen": "Mechelen", "Zaventem": "Zaventem", "Diegem": "Diegem",
                 "Machelen": "Machelen", "Wavre": "Wavre", "Louvain-la-Neuve": "Louvain-la-Neuve",
                 "Liège": "Liège", "Liege": "Liège"}
        for text, city in cases.items():
            with self.subTest(text=text):
                codes, cities = loc(text)
                self.assertEqual(codes, ["BE"])
                self.assertIn(city, cities)

    def test_louvain_la_neuve_is_not_leuven(self):
        self.assertNotIn("Leuven", loc("Louvain-la-Neuve")[1])

    def test_belgian_luxembourg_province_is_belgium_not_luxembourg(self):
        for text in ["Arlon", "Bastogne", "Marche-en-Famenne", "Bastogne, Luxembourg, Belgium",
                     "Province de Luxembourg", "Arlon, Belgium"]:
            with self.subTest(text=text):
                self.assertEqual(loc(text)[0], ["BE"])
        self.assertEqual(loc("Luxembourg City, Luxembourg")[0], ["LU"])

    def test_look_alikes(self):
        for text in ["Brussels, WI", "Brussels, Ontario", "Ghent, NY", "Ghent, Kentucky", "Antwerp, OH",
                     "Mechelen, Netherlands"]:
            with self.subTest(text=text):
                self.assertNotIn("BE", loc(text)[0])

    def test_bern_canton_code_is_not_belgium(self):
        self.assertEqual(loc("Ittigen, BE")[0], ["CH"])
        self.assertEqual(loc("Office, BEL")[0], ["BE"])


class TestGermany(unittest.TestCase):
    def test_cities(self):
        cases = {"Berlin, Germany": "Berlin", "München": "Munich", "Munich": "Munich", "Hamburg": "Hamburg",
                 "Frankfurt am Main": "Frankfurt", "Köln": "Cologne", "Düsseldorf": "Düsseldorf",
                 "Stuttgart": "Stuttgart", "Walldorf": "Walldorf", "Schwalbach am Taunus": "Frankfurt"}
        for text, city in cases.items():
            with self.subTest(text=text):
                codes, cities = loc(text)
                self.assertEqual(codes, ["DE"])
                self.assertIn(city, cities)

    def test_look_alikes(self):
        for text in ["New Berlin, WI", "Berlin, CT", "Hamburg, NY", "Hanover, NH", "Dresden, OH",
                     "Heidelberg, Victoria, Australia", "Freiburg, Switzerland", "Germantown, MD",
                     "Wilmington, DE", "Frankfort, KY"]:
            with self.subTest(text=text):
                self.assertNotIn("DE", loc(text)[0])

    def test_baden_is_swiss_baden_baden_is_german(self):
        self.assertEqual(loc("Baden, Aargau")[0], ["CH"])
        self.assertEqual(loc("Baden-Baden")[0], ["DE"])


class TestUnitedKingdom(unittest.TestCase):
    def test_cities_and_names(self):
        cases = {"London, United Kingdom": "London", "Canary Wharf": "London", "Manchester": "Manchester",
                 "Edinburgh, Scotland": "Edinburgh", "Cambridge, UK": "Cambridge", "Reading": "Reading",
                 "Belfast, Northern Ireland": "Belfast"}
        for text, city in cases.items():
            with self.subTest(text=text):
                codes, cities = loc(text)
                self.assertEqual(codes, ["UK"])
                self.assertIn(city, cities)
        for text in ["United Kingdom", "UK - Remote", "England", "Office, GB"]:
            with self.subTest(text=text):
                self.assertEqual(loc(text)[0], ["UK"])

    def test_look_alikes(self):
        for text in ["London, Ontario", "London, ON, Canada", "New London, CT", "Manchester, NH",
                     "Birmingham, AL", "Cambridge, MA", "Cambridge, Massachusetts, United States",
                     "Oxford, MS", "Reading, PA", "Bristol, CT", "Newcastle, NSW", "New England",
                     "Sydney, New South Wales", "Dublin, Ireland"]:
            with self.subTest(text=text):
                self.assertNotIn("UK", loc(text)[0])

    def test_us_places_never_match_through_city_names(self):
        for text, code in [("Cambridge (US), Massachusetts, United States", "UK"),
                           ("USA - Massachusetts - Cambridge (320 Bent Street)", "UK"),
                           ("USA - North Carolina - Durham (Old Oxford)", "UK"), ("Charleroi USA", "BE"),
                           ("Berlin, Connecticut", "DE"), ("London, Ontario, Canada", "UK")]:
            with self.subTest(text=text):
                self.assertNotIn(code, loc(text)[0])
        self.assertEqual(loc("Zurich, Switzerland; Boston, USA")[0], ["CH"])   # explicit country name still counts

    def test_region_in_title_only_does_not_count(self):
        p = Posting(provider="x", company="X", token="x", job_id="1", url="u",
                    title="Marketing Intern - UK & Ireland", locations=["Dublin, Ireland"])
        self.assertEqual(CLF.classify(p).countries, ["IE"])     # the location counts (Ireland), the title's "UK" does not


if __name__ == "__main__":
    unittest.main()
