"""Pay stated in a posting, normalised to gross EUR per month. Deterministic.

parse_pay(title, description, rates) -> Pay | None
  month:      gross EUR per month (the voluntary-internship rate when two are given; a range's lower end)
  month_max:  upper end of a range, if any
  compulsory: the separate rate for a compulsory internship (Pflichtpraktikum), if stated
  text:       the phrase as written (shown on hover)
  basis:      month | year | hour (as stated; years are /12, hours x hours_per_month)

An amount counts only with a currency (€, EUR, CHF, £, GBP, AED) and a pay word nearby (brutto, gross,
salary, Gehalt, Vergütung, compensation, stipend ...) or a period ("per month", "/Monat", "p.a.").
Revenue-style figures ("€ 5 billion", "Mio.") are ignored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CUR = r"(?P<cur{n}>€|EUR|CHF|Fr\.|SFr\.?|£|GBP|AED)"
NUM = r"(?P<num{n}>\d{{1,3}}(?:[.,'’  ]\d{{3}})+(?:[.,]\d{{1,2}}|,[-–])?|\d{{3,6}}(?:[.,]\d{{1,2}}|,[-–])?|\d{{2,3}}(?:[.,]\d)?\s?[kK](?![a-z])|\d{{2}}(?:[.,]\d{{1,2}})?)"


def _amount(n):
    return CUR.format(n=n) + r"\s?" + NUM.format(n=n)


def _amount_after(n):
    return NUM.format(n=n) + r"\s?" + CUR.format(n=n)


RANGE_SEP = r"\s?(?:[-–—]|bis|to|und|and|à|tot)\s?"
_RX = re.compile(
    rf"(?:{_amount(1)}(?:{RANGE_SEP}(?:{CUR.format(n=2)}\s?)?{NUM.format(n=2)})?"
    rf"|{NUM.format(n=3)}(?:{RANGE_SEP}{NUM.format(n=4)})?\s?{CUR.format(n=4)})"
    r"(?:\s?,-)?", re.I)
PERIOD_AFTER = {
    "month": r"^\W{0,3}(?:brutto\s+|gross\s+|netto\s+)?(?:per|pro|a|im|/|par|\bp\.?\s?)\s?(?:month|monat|mois|maand|mese|m\b)|^\W{0,3}(?:brutto|gross)?\s*(?:monthly|monatlich|mtl\.?|mensuel)|^\s?/\s?(?:mo|mon|monat|month)\b",
    "year": r"^\W{0,3}(?:brutto\s+|gross\s+)?(?:per|pro|a|im|/|par)\s?(?:year|jahr|annum|an|jaar|anno)|^\W{0,3}(?:p\.?\s?a\.?|annual(?:ly)?|yearly|jährlich|brutto(?:jahres)?)?\s*(?:p\.?\s?a\.?|annual|yearly|jährlich)\b",
    "hour": r"^\W{0,3}(?:brutto\s+|gross\s+)?(?:per|pro|an|/|par)\s?(?:hour|stunde|std|h)\b|^\W{0,3}(?:hourly|stündlich)",
}
PERIOD_BEFORE = {
    "month": r"(monatsgehalt|monatsbrutto|monthly|monatlich|per month|pro monat|mensuel|maandelijks|maandsalaris)\W*(?:\w+\W+){0,6}$",
    "year": r"(jahresgehalt|jahresbrutto|annual|yearly|per year|pro jahr|per annum|annuel|jaarsalaris)\W*(?:\w+\W+){0,6}$",
    "hour": r"(stundenlohn|hourly|per hour|pro stunde|stundensatz|uurloon)\W*(?:\w+\W+){0,6}$",
}
PAY_WORDS = re.compile(
    r"brutto|gross|salary|salaries|gehalt|vergütung|verguetung|entlohnung|bezahlung|lohn|kollektivvertrag|\bkv\b|"
    r"compensation|remuneration|stipend|allowance|\bpay\b|paid|wage|vergoeding|salaris|stagevergoeding|"
    r"r[ée]mun[ée]ration|salaire|gratification|indemnit[ée]|retribuzione|aufwandsentsch", re.I)
NOT_PAY = re.compile(r"^\s?(?:million|billion|mio|mrd|bn|milliard|mn\b|m\b|tn\b)|^\W{0,2}(?:umsatz|revenue|turnover|sales)", re.I)
COMPULSORY = re.compile(r"pflicht|compulsory|mandatory|obligator|curricular|verplicht|obligatoire", re.I)
VOLUNTARY = re.compile(r"freiwillig|voluntary|non[- ]?mandatory|non[- ]?compulsory|optional|facultati", re.I)
COMPULSORY_TITLE = re.compile(r"\b(compulsory|mandatory|obligatory) internship\b|pflichtpraktik|praxissemester", re.I)

DEFAULT_RATES = {"EUR": 1.0, "CHF": 1.06, "GBP": 1.17, "AED": 0.25}
CUR_CODE = {"€": "EUR", "eur": "EUR", "chf": "CHF", "fr.": "CHF", "sfr.": "CHF", "sfr": "CHF", "£": "GBP", "gbp": "GBP", "aed": "AED"}


@dataclass
class Pay:
    month: int
    month_max: int | None = None
    compulsory: int | None = None
    text: str = ""
    basis: str = "month"


def _num(s: str) -> float | None:
    s = s.strip().replace(" ", " ")
    k = 1000 if s[-1:].lower() == "k" else 1
    s = s.rstrip("kK ").replace(",-", "").replace(",–", "")
    m = re.fullmatch(r"(\d{1,3}(?:[.,'’ ]\d{3})+)([.,]\d{1,2})?", s)
    if m:
        return float(re.sub(r"\D", "", m.group(1)) + (("." + m.group(2)[1:]) if m.group(2) else "")) * k
    m = re.fullmatch(r"(\d+)(?:[.,](\d{1,2}))?", s)
    if m:
        return float(m.group(1) + ("." + m.group(2) if m.group(2) else "")) * k
    return None


def _candidates(text: str):
    for m in _RX.finditer(text):
        g = m.groupdict()
        cur = next((g[f"cur{i}"] for i in (1, 2, 4) if g.get(f"cur{i}")), None)
        lo = _num(g.get("num1") or g.get("num3") or "")
        hi = _num(g.get("num2") or g.get("num4") or "") if (g.get("num2") or g.get("num4")) else None
        if not cur or lo is None:
            continue
        after, before = text[m.end():m.end() + 40], text[max(0, m.start() - 120):m.start()]
        if NOT_PAY.search(after):
            continue
        basis = next((b for b, rx in PERIOD_AFTER.items() if re.search(rx, after, re.I)), None) or \
            next((b for b, rx in PERIOD_BEFORE.items() if re.search(rx, before, re.I)), None)
        if not basis and not PAY_WORDS.search(before[-100:] + text[m.end():m.end() + 60]):
            continue
        if lo < 100 and basis != "hour":
            continue                                # a small figure counts only as an hourly rate
        if not basis:
            basis = "year" if lo >= 12000 else "month"
        yield m, CUR_CODE.get(cur.lower(), CUR_CODE.get(cur, "EUR")), lo, hi, basis, before


def parse_pay(title: str, description: str, rates: dict | None = None, hours_per_month: float = 173) -> Pay | None:
    rates = {**DEFAULT_RATES, **(rates or {})}
    text = (title or "") + "\n" + (description or "")
    found = []
    for m, cur, lo, hi, basis, before in _candidates(text):
        f = {"year": 1 / 12, "hour": hours_per_month, "month": 1}[basis] * rates.get(cur, 1.0)
        mlo, mhi = round(lo * f), (round(hi * f) if hi and hi > lo else None)
        if not 300 <= mlo <= 15000:
            continue                                # not a plausible monthly internship pay
        ctx = before[-80:]
        kind = "compulsory" if COMPULSORY.search(ctx) and not VOLUNTARY.search(ctx[-40:]) else \
            "voluntary" if VOLUNTARY.search(ctx) else None
        found.append({"lo": mlo, "hi": mhi, "kind": kind, "basis": basis,
                      "text": re.sub(r"\s+", " ", text[max(0, m.start() - 40):m.end() + 25]).strip()})
    if not found:
        return None
    vol = [f for f in found if f["kind"] == "voluntary"]
    comp = [f for f in found if f["kind"] == "compulsory"]
    main = (vol or [f for f in found if f["kind"] is None] or found)[0]
    compulsory = comp[0]["lo"] if comp and comp[0] is not main else None
    text = main["text"] if compulsory is None else main["text"] + " … " + comp[0]["text"]
    return Pay(month=main["lo"], month_max=main["hi"], compulsory=compulsory, text=text[:200], basis=main["basis"])


def compulsory_only(title: str) -> bool:
    return bool(COMPULSORY_TITLE.search(title or ""))
