"""Start dates in posting text (EN/DE/FR/NL/IT), deterministic.

parse_start(title, description, ref) -> Start(label, month, asap)
  label: the phrase as written ("ab Februar 2027", "Start: 01.04.2027", "summer 2027")
  month: "YYYY-MM" (seasons and quarters map to their first month; a missing year is the next
         such month from `ref`, i.e. today), or None if unclear
  asap:  "as soon as possible", "ab sofort", "dès que possible", "per direct"

A date counts as a start only next to a start word ("starting", "ab", "dès", "vanaf", "Start:" ...)
in the description; in the title a month or season with a year is enough ("Intern - January 2027").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MONTHS = {
    1: "january jan januar jänner janvier janv janvier januari gennaio",
    2: "february feb februar février fevrier févr februari febbraio",
    3: "march mar märz maerz mrz mars maart marzo",
    4: "april apr avril aprile",
    5: "may mai mei maggio",
    6: "june jun juni juin giugno",
    7: "july jul juli juillet juil luglio",
    8: "august aug août aout augustus agosto",
    9: "september sep sept septembre settembre",
    10: "october oct okt oktober octobre ottobre",
    11: "november nov novembre",
    12: "december dec dez dezember décembre decembre dicembre",
}
SEASONS = {   # season -> first month
    3: "spring frühling frühjahr fruehjahr printemps voorjaar lente primavera",
    6: "summer sommer été ete zomer estate",
    9: "autumn fall herbst automne najaar herfst autunno",
    1: "winter hiver inverno",
}
_MONTH = {w: n for n, ws in MONTHS.items() for w in ws.split()}
_SEASON = {w: n for n, ws in SEASONS.items() for w in ws.split()}

def _alt(words):
    return "|".join(sorted(map(re.escape, words), key=len, reverse=True))

M = rf"(?<!\w)(?P<mon>{_alt(_MONTH)})(?!\w)\.?"     # whole words only ("Abfall" is not "ab fall")
S = rf"(?<!\w)(?P<sea>{_alt(_SEASON)})(?!\w)"
def Y(n):
    return rf"(?P<year{n}>20\d\d|'\d\d)"
QUAL = r"(?:(?:early|mid|late|beginning of|end of|anfang|mitte|ende|début|debut|mi-|fin|begin|eind|half|inizio)\s*)?"
DATE = (rf"(?P<dmy>(?P<d>\d{{1,2}})[./](?P<m>\d{{1,2}})[./](?P<y>20\d\d|\d\d))(?!\d)"
        rf"|(?P<iso>(?P<iy>20\d\d)-(?P<im>\d\d)-\d\d)"
        rf"|(?P<my>(?P<m2>0?[1-9]|1[0-2])[./](?P<y2>20\d\d))(?!\d)"
        rf"|(?:\d{{1,2}}(?:st|nd|rd|th|er|\.)?\s+)?{QUAL}{M}(?:\s*,?\s*(?:of\s+)?{Y(1)})?"
        rf"|{QUAL}{S}(?:\s+(?:of\s+)?{Y(2)})?"
        rf"|(?P<q>q[1-4])\s*{Y(3)}")
ASAP = (r"as soon as possible|asap|immediately|ab sofort|sofort|per sofort|zum nächstmöglichen zeitpunkt|"
        r"dès que possible|des que possible|immédiatement|au plus vite|per direct|zo snel mogelijk|z\.s\.m\.|"
        r"il prima possibile|da subito")
START_WORDS = (r"start(?:ing|s)?(?:\s+(?:date|in|on|from|as of|at))?|start ?date|commenc(?:e|ing|ement)|beginning(?: in| on| of)?|"
               r"available from|as of|as from|from|ab(?: dem)?|zum|per|beginn|eintritt(?:sdatum|stermin)?|"
               r"startdatum|starttermin|einstieg|dès|des|à partir d[eu']|a partir d[eu']|à compter d[eu']|"
               r"date de début|début|démarrage|vanaf|aanvang|ingangsdatum|begindatum|inizio|dal|a partire da")
_RX_DATE = re.compile(DATE, re.I)
# "Summer Internship 2027", "Sommerpraktikum 2027": a season with a year a few words later
_RX_SEASON_YEAR = re.compile(rf"(?<![\w-])(?P<sea>{_alt(_SEASON)})\w*(?:\W+[\w&']+){{0,3}}?\W+(?P<year1>20\d\d)\b", re.I)
_RX_CTX = re.compile(rf"(?<![\w-])(?:{START_WORDS})\s*[:\-–]?\s*(?:(?:the|le|la|den|dem|der|de|il)\s+)?(?:(?:1st|1er|1\.?)\s+(?:of\s+)?)?$", re.I)
_RX_NOT_START = re.compile(r"graduat|abschluss|abschliess|diplôm|diplom|afstudeer|apply|application|bewerb|deadline|"
                           r"postul|sollicit|recruiting|until|bis|jusqu|tot ", re.I)
_RX_ASAP = re.compile(rf"(?<![\w-])(?:(?:{START_WORDS})\s*[:\-–]?\s*)?(?:{ASAP})(?![\w-])", re.I)
_RX_ASAP_CTX = re.compile(rf"(?:{START_WORDS}|internship|praktikum|stage|stagiaire|position|role)\W{{0,25}}$", re.I)


@dataclass
class Start:
    label: str | None = None
    month: str | None = None      # "YYYY-MM"
    asap: bool = False
    explicit: bool = False        # the year was written (only then can the start be "in the past")
    pos: int = 0                  # where the phrase was found (internal)


def _year(s: str) -> int:
    return 2000 + int(s[-2:]) if len(s) <= 3 else int(s)


def _explicit(m: re.Match, text_after: str = "") -> bool:
    g = m.groupdict()
    return bool(g.get("year1") or g.get("year2") or g.get("year3") or g.get("dmy") or g.get("iso") or g.get("my")
                or re.match(r"\W{0,3}(?:[\wäéû.]+\W{1,3}){0,4}?(20\d\d)\b", text_after))


def _month_of(m: re.Match, text_after: str, ref: date) -> str | None:
    g = m.groupdict()
    g["year"] = g.get("year1") or g.get("year2") or g.get("year3")
    if g.get("dmy"):
        mon, yr = int(g["m"]), _year(g["y"])
    elif g.get("iso"):
        mon, yr = int(g["im"]), int(g["iy"])
    elif g.get("my"):
        mon, yr = int(g["m2"]), int(g["y2"])
    elif g.get("q"):
        mon, yr = (int(g["q"][1]) - 1) * 3 + 1, _year(g["year"])
    else:
        mon = _MONTH.get((g.get("mon") or "").lower()) or _SEASON.get((g.get("sea") or "").lower())
        if not mon:
            return None
        if g.get("year"):
            yr = _year(g["year"])
        else:   # "from January to June 2027": take the year that follows; otherwise the next such month
            nxt = re.match(r"\W{0,3}(?:[\wäéû.]+\W{1,3}){0,4}?(20\d\d)\b", text_after)
            yr = int(nxt.group(1)) if nxt else (ref.year if mon >= ref.month else ref.year + 1)
    if not 1 <= mon <= 12:
        return None
    return f"{yr:04d}-{mon:02d}"


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" -–:,.")[:60]


def parse_start(title: str, description: str = "", ref: date | None = None) -> Start:
    ref = ref or date.today()
    # Title: a month/season/quarter with a year is the start ("Transfer Pricing Intern – January 2027").
    for m in _RX_DATE.finditer(title or ""):
        g = m.groupdict()
        year = g.get("year1") or g.get("year2") or g.get("year3")
        if (g.get("mon") or g.get("sea") or g.get("q")) and year or g.get("dmy") or g.get("iso"):
            ctx = _RX_CTX.search(title[max(0, m.start() - 40):m.start()])
            return Start(_clean((ctx.group(0) if ctx else "") + m.group(0)), _month_of(m, "", ref), explicit=True)
    m = _RX_SEASON_YEAR.search(title or "")
    if m:
        return Start(_clean(m.group(0)), _month_of(m, "", ref), explicit=True)
    text = (title or "") + "\n" + (description or "")
    best = None
    for m in _RX_DATE.finditer(text):
        ctx = _RX_CTX.search(text[max(0, m.start() - 45):m.start()])
        if not ctx:
            continue
        g = m.groupdict()
        if g.get("mon") and not g.get("year1") and len(g["mon"]) <= 3 and g["mon"].lower() in ("mar", "may", "mai", "mei", "jun", "jul", "dec", "des"):
            continue   # bare short words ("per mai", "from mar") are too ambiguous without a year
        month = _month_of(m, text[m.end():m.end() + 40], ref)
        if month:
            best = Start(_clean(ctx.group(0) + m.group(0)), month, explicit=_explicit(m, text[m.end():m.end() + 40]))
            best.pos = m.start()
            break
    for a in _RX_ASAP.finditer(text):
        if best and best.pos < a.start():
            break                                  # a dated start comes first
        led = re.match(rf"(?:{START_WORDS})\b", a.group(0), re.I)
        if led or _RX_ASAP_CTX.search(text[max(0, a.start() - 30):a.start()]):
            return Start(_clean(a.group(0)), None, True)
    if not best:   # a season with its year ("summer 2027") is a start even without a start word,
        for m in re.finditer(rf"(?<![\w-]){QUAL}{S}\s+(?:of\s+)?{Y(2)}\b", description or "", re.I):
            if _RX_NOT_START.search(description[max(0, m.start() - 60):m.start()]):
                continue   # ...but not a graduation or application date ("you will graduate between fall 2026 and ...")
            best = Start(_clean(m.group(0)), _month_of(m, "", ref), explicit=True)
            break
    return best or Start()


def is_past(month: str | None, today: date | None = None) -> bool:
    today = today or date.today()
    return bool(month) and month < f"{today.year:04d}-{today.month:02d}"


# ------------------------------------------------------------------ application deadlines
# A date counts as a deadline only right after a deadline phrase ("Application deadline: 15 December 2026",
# "Bewerbungsschluss 15.12.2026", "date limite de candidature : 15 décembre", "uiterlijk 15 december").
DEADLINE_WORDS = (r"application deadline|applications? (?:close|closes|closing|are accepted until|open until|due)(?: date)?(?: on| by)?|"
                  r"deadline(?: for applications?| to apply)?|closing date(?: for applications)?|apply (?:by|before|until|no later than)|"
                  r"submit (?:your|an) application (?:by|before|until)|"
                  r"bewerbungs(?:schluss|frist|ende)|bewirb dich (?:bis|bitte bis)(?: zum)?|bewerbungen (?:bis|werden bis)(?: zum)?|"
                  r"date limite(?: de (?:candidature|dépôt|depot))?|candidatures? (?:jusqu'au|avant le)|postulez avant le|"
                  r"sluitingsdatum|reageren (?:kan )?(?:tot|uiterlijk)|solliciteren (?:kan )?(?:tot|uiterlijk)|uiterlijk|"
                  r"scadenza(?: candidature)?|candidature entro il")
_NUM_DATE = r"(?P<d>\d{1,2})[./](?P<m>\d{1,2})[./](?P<y>20\d\d|\d\d)(?!\d)|(?P<iy>20\d\d)-(?P<im>\d\d)-(?P<id>\d\d)"
_DAY_MON = rf"(?P<d2>\d{{1,2}})(?:st|nd|rd|th|er|\.)?\s+(?:of\s+)?(?P<mon2>{_alt(_MONTH)})(?!\w)\.?,?(?:\s+(?P<y3>20\d\d))?"
_MON_DAY = rf"(?P<mon3>{_alt(_MONTH)})(?!\w)\.?\s+(?P<d3>\d{{1,2}})(?:st|nd|rd|th)?(?!\d),?(?:\s+(?P<y4>20\d\d))?"
_RX_DEADLINE = re.compile(rf"(?<![\w-])(?:{DEADLINE_WORDS})\s*(?:(?:is|ist|est|:|-|–|on|am|le|op|il|the|der|den|dem|zum|de)(?!\w)\s*){{0,3}}"
                          rf"(?:(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|montag|dienstag|mittwoch|"
                          rf"donnerstag|freitag|samstag|sonntag|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche),?\s+)?"
                          rf"(?:the\s+)?(?:{_NUM_DATE}|{_DAY_MON}|{_MON_DAY})", re.I)


@dataclass
class Deadline:
    label: str | None = None      # the phrase as written
    date: str | None = None       # "YYYY-MM-DD"


def parse_deadline(description: str = "", ref: date | None = None) -> Deadline:
    """The first application deadline stated in the description, or an empty Deadline."""
    ref = ref or date.today()
    for m in _RX_DEADLINE.finditer(description or ""):
        g = m.groupdict()
        if g.get("d"):
            d, mon, yr = int(g["d"]), int(g["m"]), _year(g["y"])
            if mon > 12 and d <= 12:          # US order (12/15/2026)
                d, mon = mon, d
        elif g.get("iy"):
            d, mon, yr = int(g["id"]), int(g["im"]), int(g["iy"])
        else:
            d = int(g.get("d2") or g.get("d3"))
            mon = _MONTH[(g.get("mon2") or g.get("mon3")).lower()]
            y = g.get("y3") or g.get("y4")
            yr = int(y) if y else (ref.year if (mon, d) >= (ref.month, ref.day) else ref.year + 1)
        try:
            when = date(yr, mon, d)
        except ValueError:
            continue
        return Deadline(_clean(m.group(0)), when.isoformat())
    return Deadline()
