"""Degree and language requirements, extracted deterministically from a posting description."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_SENTENCE = re.compile(r"(?<=[.!?;])\s+|\n+|•|·|•")
_CLAUSE = re.compile(r"[,;:()/\[\]]|\s[–—-]\s")


@dataclass
class Reqs:
    degree: str = "unclear"            # bachelor_ok | master_required | unclear
    degree_note: str | None = None     # the sentence that decided it (shortened)
    lang_required: list[str] = field(default_factory=list)
    lang_plus: list[str] = field(default_factory=list)


class RequirementExtractor:
    def __init__(self, cfg: dict):
        r = cfg.get("requirements") or {}
        self.optional = re.compile(r.get("optional", r"(?!x)x"), re.I)
        d = r.get("degree") or {}
        self.master = [re.compile(p, re.I) for p in d.get("master", [])]
        self.bachelor = [re.compile(p, re.I) for p in d.get("bachelor", [])]
        self.bachelor_done = re.compile(d.get("bachelor_completed", r"(?!x)x"), re.I)
        lang = r.get("languages") or {}
        self.lang_names = {code: re.compile(r"(?<!\w)(" + "|".join(pats) + r")(?!\w)", re.I)
                           for code, pats in (lang.get("names") or {}).items()}
        self.not_language = re.compile(lang.get("not_language", r"(?!x)x"), re.I)
        self.required = re.compile(lang.get("required", r"(?!x)x"), re.I)

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [s.strip() for s in _SENTENCE.split(text or "") if s and s.strip()]

    # ------------------------------------------------------------ degree
    def degree(self, text: str) -> tuple[str, str | None]:
        master_note = bachelor_note = None
        bachelor_open = bachelor_done = False
        for sent in self._sentences(text):
            for clause in _CLAUSE.split(sent):
                if not clause.strip() or self.optional.search(clause):
                    continue          # "a master's degree is a plus" does not make it required
                if any(r.search(clause) for r in self.master) and not master_note:
                    master_note = sent
                if any(r.search(clause) for r in self.bachelor):
                    if self.bachelor_done.search(sent):
                        bachelor_done = True
                    else:
                        bachelor_open = True
                    bachelor_note = bachelor_note or sent
        if bachelor_open:
            return "bachelor_ok", _short(bachelor_note)
        if master_note:
            return "master_required", _short(master_note)
        if bachelor_done:
            return "bachelor_ok", _short(bachelor_note)   # graduates with a bachelor's can apply
        return "unclear", None

    # ------------------------------------------------------------ languages
    def languages(self, text: str) -> tuple[list[str], list[str]]:
        required, plus = set(), set()
        for sent in self._sentences(text):
            clean = self.not_language.sub(" ", sent)
            if not any(rx.search(clean) for rx in self.lang_names.values()):
                continue
            s_plus, s_req = bool(self.optional.search(clean)), bool(self.required.search(clean))
            for clause in _CLAUSE.split(clean):
                codes = [c for c, rx in self.lang_names.items() if rx.search(clause)]
                if not codes:
                    continue
                c_plus, c_req = bool(self.optional.search(clause)), bool(self.required.search(clause))
                if c_plus:                       # "German is a plus" (even if also "fluent")
                    plus.update(codes)
                elif c_req:
                    required.update(codes)
                elif s_plus and not s_req:       # "English: fluent" splits the qualifier into its own clause
                    plus.update(codes)
                elif s_req and not s_plus:
                    required.update(codes)
                # bare mentions ("applications in English") count as neither
        return sorted(required), sorted(plus - required)

    def extract(self, text: str) -> Reqs:
        deg, note = self.degree(text)
        req, plus = self.languages(text)
        return Reqs(degree=deg, degree_note=note, lang_required=req, lang_plus=plus)


def _short(s: str | None, n: int = 140) -> str | None:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"
