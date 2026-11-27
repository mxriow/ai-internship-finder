"""Deterministic classifiers: internship type, location, function category, language."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .dates import is_past, parse_deadline, parse_start
from .models import Posting
from .pay import compulsory_only, parse_pay
from .requirements import RequirementExtractor


def _rx(patterns, flags=re.I):
    return [re.compile(p, flags) for p in patterns or []]


def _any(rxs, text):
    return any(r.search(text) for r in rxs)


@dataclass
class Result:
    intern_type: str | None = None      # intern | working_student | trainee
    countries: list[str] = field(default_factory=list)   # matched target country codes
    cities: list[str] = field(default_factory=list)
    category: str | None = None
    needs_review: bool = False
    review_reason: str | None = None
    language: str | None = None
    duration: str | None = None
    start: str | None = None            # the start phrase as written
    start_month: str | None = None      # "YYYY-MM", None if unclear
    start_asap: bool = False
    stale: bool = False                 # the stated start date has already passed
    pay: int | None = None              # gross EUR per month (voluntary rate when two are given; range: lower end)
    pay_max: int | None = None
    pay_compulsory: int | None = None   # separate rate for a compulsory internship
    pay_text: str | None = None
    pay_basis: str | None = None        # month | year | hour, as stated
    compulsory_only: bool = False       # titled "Compulsory Internship" / "Pflichtpraktikum"
    degree: str = "unclear"
    degree_note: str | None = None
    lang_required: list[str] = field(default_factory=list)
    lang_plus: list[str] = field(default_factory=list)
    deadline: str | None = None         # application deadline stated in the description, YYYY-MM-DD
    deadline_text: str | None = None


class Classifier:
    def __init__(self, cfg: dict):
        it = cfg["internship"]
        self.intern = {k: _rx(it.get(k)) for k in ("intern", "working_student", "trainee", "graduate")}
        self.not_intern = _rx(it.get("not_internship"))
        self.not_graduate = _rx(it.get("not_graduate"))
        self.emp_types = {k: _rx(v) for k, v in it.get("employment_types", {}).items()}

        self.countries = {}
        for code in cfg["target_countries"]:
            c = cfg["countries"][code]
            suffix = c.get("suffix_codes", c.get("codes", []))
            self.countries[code] = {
                "codes": {x.upper() for x in c.get("codes", [])},
                "suffix": re.compile(rf"(?:^|[,(\s/-])(?:{'|'.join(map(re.escape, suffix))})\)?$") if suffix else None,
                "names": _rx([rf"(?<!\w){re.escape(n)}(?!\w)" for n in c.get("names", [])]),
                "cities": {city: _rx([rf"(?<![\w-]){p}(?![\w-])" for p in pats])
                           for city, pats in c.get("cities", {}).items()},
                "not_here": _rx(c.get("not_here")),
            }

        self.city_blockers = _rx(cfg.get("city_match_blockers"), 0)
        self.categories = {k: _rx(v) for k, v in cfg["categories"].items()}
        self.excluded_hard = _rx(cfg["excluded_hard"])
        self.excluded = _rx(cfg["excluded_soft"]) + _rx(cfg.get("excluded_case_sensitive"), 0) + self.excluded_hard
        self.desc_min = cfg.get("description_min_hits", 3)

        lang = cfg["language"]
        self.lang_markers = {k: _rx(v) for k, v in lang.get("title_markers", {}).items()}
        self.stopwords = {k: set(v) for k, v in lang["stopwords"].items()}
        self.lang_min = lang.get("min_hits", 5)

        ex = cfg.get("extract", {})
        self.rx_duration = _rx(ex.get("duration"))
        self.dur_ignore_after = re.compile(ex["duration_ignore_after"], re.I) if ex.get("duration_ignore_after") else None
        self.dur_ignore_before = re.compile(ex["duration_ignore_before"], re.I) if ex.get("duration_ignore_before") else None
        self.review_if_generic = _rx(cfg.get("review_if_generic"))
        self.reqs = RequirementExtractor(cfg)
        self.pay_cfg = cfg.get("pay", {})

    # ------------------------------------------------------------ internship
    def intern_type(self, title: str, employment_raw: str | None = None) -> str | None:
        """intern | working_student | trainee | graduate, or None.

        The not_internship guards ("early-stage startup", "Stage Manager") only cancel a match found
        in the title; the feed's own employment-type field is still checked.
        """
        if not _any(self.not_intern, title):
            for kind in ("working_student", "trainee", "intern"):
                if _any(self.intern[kind], title):
                    return kind
            if _any(self.intern["graduate"], title) and not _any(self.not_graduate, title):
                return "graduate"
        if employment_raw:
            for kind in ("working_student", "trainee", "intern", "graduate"):
                if _any(self.emp_types.get(kind, []), employment_raw):
                    return kind
        return None

    # ------------------------------------------------------------ location
    def location(self, locations: list[str], country_codes: list[str] | None = None):
        """Return ([matching country codes], [canonical cities]); ([], []) if none.

        A multi-location posting can match several target countries.
        """
        found, cities = [], []
        feed_codes = {x.upper() for x in country_codes or []}
        listed = [l for l in locations if l and l.strip()]
        if listed and all(_any(self.city_blockers, l) for l in listed):
            feed_codes = set()   # every location is plainly elsewhere (USA, Canada...): the feed's country facet is wrong
                                 # (MSD's Workday UK filter returns "USA - Pennsylvania - North Wales" postings)
        for code, c in self.countries.items():
            hit = bool(c["codes"] & feed_codes)
            for loc in locations:
                if not loc or _any(c["not_here"], loc):
                    continue
                if _any(c["names"], loc) or (c["suffix"] and c["suffix"].search(loc.strip())):
                    hit = True
                if _any(self.city_blockers, loc):
                    continue                     # e.g. "Cambridge, Massachusetts, United States"
                for city, rxs in c["cities"].items():
                    m = next((r.search(loc) for r in rxs if r.search(loc)), None)
                    if m:
                        hit = True
                        name = m.group(0).strip().title() if city == "Other" else city  # catch-all group: show the town
                        if name not in cities:
                            cities.append(name)
            if hit:
                found.append(code)
        return found, cities

    # ------------------------------------------------------------ category
    def _title_category(self, title: str) -> str | None:
        for cat, rxs in self.categories.items():
            if _any(rxs, title):
                return cat
        return None

    def category(self, title: str, description: str = "", department: str | None = None):
        """Return (category, needs_review, reason)."""
        if _any(self.excluded_hard, title):
            return "excluded", False, None
        cat = self._title_category(title)
        excluded = _any(self.excluded, title)
        if cat and excluded:
            return cat, True, "title mixes business and technical/excluded terms"
        if excluded:
            return "excluded", False, None
        if cat == "other_business" and _any(self.review_if_generic, title):
            return cat, True, "generic education-level internship (e.g. HBO/WO-stage), function unclear"
        if cat:
            return cat, False, None
        if department:
            dcat = self._title_category(department)
            if _any(self.excluded, department):
                return "excluded", True, f"generic title, excluded department '{department}'"
            if dcat:
                return dcat, True, f"category from department '{department}'"
        scores = {k: sum(len(r.findall(description)) for r in rxs) for k, rxs in self.categories.items()}
        best = max(scores, key=scores.get) if description else None
        technical = sum(len(r.findall(description)) for r in self.excluded) if description else 0
        if best and technical >= self.desc_min and technical > scores[best]:
            return "excluded", True, f"generic title, technical description ({technical} technical vs {scores[best]} business hits)"
        if best and scores[best] >= self.desc_min:
            return best, True, f"category from description ({scores[best]} hits)"
        return "other_business", True, "no category signal in title or description"

    # ------------------------------------------------------------ language
    def language(self, title: str, description: str = "", declared: str | None = None) -> str | None:
        """Description stopwords first; feed-declared language is often a board default."""
        words = re.findall(r"[a-zà-ÿ]+", description.lower())
        if words:
            counts = {k: sum(1 for w in words if w in sw) for k, sw in self.stopwords.items()}
            best = max(counts, key=counts.get)
            if counts[best] >= self.lang_min:
                return best.upper()
        for lang, rxs in self.lang_markers.items():
            if _any(rxs, title):
                return lang.upper()
        if declared and declared[:2].lower() in self.stopwords:
            return declared[:2].upper()
        if re.fullmatch(r"[\x00-\x7f]+", title or "") and re.search(r"\b(intern|internship|working student)\b", title, re.I):
            return "EN"
        return None

    # ------------------------------------------------------------ extraction
    def duration(self, text: str) -> str | None:
        """First duration that is not about benefits, notice periods or required experience."""
        for r in self.rx_duration:
            for m in r.finditer(text):
                before, after = text[max(0, m.start() - 45):m.start()], text[m.end():m.end() + 25]
                if self.dur_ignore_before and self.dur_ignore_before.search(before):
                    continue
                if self.dur_ignore_after and self.dur_ignore_after.search(after):
                    continue
                return re.sub(r"\s+", " ", m.group(0)).strip()[:60]
        return None

    # ------------------------------------------------------------ all together
    def classify(self, p: Posting) -> Result:
        res = Result(intern_type=self.intern_type(p.title, p.employment_raw))
        if not res.intern_type:
            return res
        res.countries, res.cities = self.location(p.locations, p.country_codes)
        res.category, res.needs_review, res.review_reason = self.category(p.title, p.description, p.department)
        res.language = self.language(p.title, p.description, p.language)
        text = p.title + "\n" + p.description
        res.duration = self.duration(text)
        if p.description:
            r = self.reqs.extract(p.description)
            res.degree, res.degree_note, res.lang_required, res.lang_plus = (
                r.degree, r.degree_note, r.lang_required, r.lang_plus)
        st = parse_start(p.title, p.description)     # a month without a year: its next occurrence from today
        res.start, res.start_month, res.start_asap = st.label, st.month, st.asap
        res.stale = st.explicit and is_past(st.month)
        pay = parse_pay(p.title, p.description, self.pay_cfg.get("eur_rates"), self.pay_cfg.get("hours_per_month", 173))
        if pay:
            res.pay, res.pay_max, res.pay_compulsory, res.pay_text, res.pay_basis = (
                pay.month, pay.month_max, pay.compulsory, pay.text, pay.basis)
        res.compulsory_only = compulsory_only(p.title)
        dl = parse_deadline(p.description)
        res.deadline, res.deadline_text = dl.date, dl.label
        return res
