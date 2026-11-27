"""Pay extraction (finder/pay.py): normalised to gross EUR per month."""
import unittest

from finder.pay import compulsory_only, parse_pay


def pay(desc, title="Intern"):
    return parse_pay(title, desc)


class TestPay(unittest.TestCase):
    def test_user_examples(self):
        self.assertEqual(pay("Das Mindestgehalt beträgt €2.798 brutto pro Monat.").month, 2798)
        self.assertEqual(pay("Wir bieten €2.798 brutto.").month, 2798)
        self.assertEqual(pay("The salary is EUR 1.617,- gross monthly.").month, 1617)
        self.assertEqual(pay("Bruttomonatsgehalt: EUR 2.100").month, 2100)
        p = pay("Remuneration: min. € 1.070 per month on a full-time basis.")
        self.assertEqual((p.month, p.basis), (1070, "month"))
        p = pay("Vergütung: 1.050–2.270 €/Monat je nach Studienfortschritt.")
        self.assertEqual((p.month, p.month_max), (1050, 2270))

    def test_annual_and_hourly(self):
        p = pay("The annual gross salary is EUR 42.000.")
        self.assertEqual((p.month, p.basis), (3500, "year"))
        self.assertEqual(pay("Jahresbruttogehalt von € 36.000 (Vollzeit).").month, 3000)
        self.assertEqual(pay("€30k per year").month, 2500)
        p = pay("Working students earn €15 per hour.")
        self.assertEqual((p.month, p.basis), (15 * 173, "hour"))

    def test_other_currencies(self):
        self.assertEqual(pay("Salary: CHF 2'500 per month").month, round(2500 * 1.06))
        self.assertEqual(pay("We pay £2,000 per month.").month, round(2000 * 1.17))

    def test_voluntary_and_compulsory(self):
        p = pay("Pflichtpraktikum: € 1.070 brutto/Monat. Freiwilliges Praktikum: € 2.100 brutto/Monat.")
        self.assertEqual((p.month, p.compulsory), (2100, 1070))
        p = pay("For a voluntary internship we pay EUR 2.300 gross per month; for a compulsory internship EUR 1.200.")
        self.assertEqual((p.month, p.compulsory), (2300, 1200))
        self.assertTrue(compulsory_only("Compulsory Internship Marketing (m/f/d)"))
        self.assertTrue(compulsory_only("Pflichtpraktikum im Vertrieb"))
        self.assertFalse(compulsory_only("Marketing Internship"))

    def test_not_pay(self):
        self.assertIsNone(pay("We had €5 billion revenue in 2025."))
        self.assertIsNone(pay("A company with a turnover of EUR 3.000 Mio."))
        self.assertIsNone(pay("Founded in 2010 with 1.200 employees in 30 countries."))
        self.assertIsNone(pay("Budget responsibility of € 2.000.000."))


if __name__ == "__main__":
    unittest.main()
