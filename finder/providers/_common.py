"""Settings shared by the API providers added for Oracle, Eightfold and Taleo (set by pipeline.configure_providers)."""
from __future__ import annotations

targets: dict[str, list[str]] = {}       # country code -> names, e.g. {"CH": ["Switzerland", "Schweiz", ...]}
target_codes: set[str] = set()           # ISO codes feeds may use: CH, CHE, GB, GBR, UK, ...
detail_filter = lambda title, employment=None: True  # noqa: E731  fetch descriptions only for internship-like titles


def configure(country_targets=None, codes=None, details=None):
    global targets, target_codes, detail_filter
    if country_targets is not None:
        targets = country_targets
    if codes is not None:
        target_codes = {c.upper() for c in codes}
    if details is not None:
        detail_filter = details


class PostingList(list):
    total = 0   # all postings on the board, any country (used by verify)
