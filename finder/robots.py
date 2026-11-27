"""robots.txt matching per RFC 9309: user-agent groups, `*` and `$` patterns, longest match wins.

(Python's urllib.robotparser ignores `*`/`$` wildcards and uses first-match order.)
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit


class Robots:
    def __init__(self, text: str, agent: str):
        self.agent = agent.lower()
        self.rules: list[tuple[bool, str, re.Pattern]] = []   # (allow, raw pattern, compiled)
        self.crawl_delay: float | None = None
        groups, current, in_rules = [], None, False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (x.strip() for x in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if current is None or in_rules:          # a new group starts
                    current = {"agents": [], "rules": [], "delay": None}
                    groups.append(current)
                    in_rules = False
                current["agents"].append(value.lower())
            elif key in ("allow", "disallow") and current is not None:
                in_rules = True
                if value:                                  # an empty Disallow allows everything
                    current["rules"].append((key == "allow", value))
            elif key == "crawl-delay" and current is not None:
                in_rules = True
                try:
                    current["delay"] = float(value)
                except ValueError:
                    pass
        # Our group: every group naming our product token; otherwise every "*" group.
        mine = [g for g in groups if any(a != "*" and a in self.agent for a in g["agents"])]
        chosen = mine or [g for g in groups if "*" in g["agents"]]
        for g in chosen:
            for allow, pattern in g["rules"]:
                self.rules.append((allow, pattern, _compile(pattern)))
            if g["delay"] is not None:
                self.crawl_delay = g["delay"]

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        path = unquote(parts.path or "/") + (("?" + unquote(parts.query)) if parts.query else "")
        best_len, best_allow = -1, True
        for allow, pattern, rx in self.rules:
            if rx.match(path):
                length = len(pattern)
                if length > best_len or (length == best_len and allow):
                    best_len, best_allow = length, allow
        return best_allow


def _compile(pattern: str) -> re.Pattern:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in unquote(body))
    return re.compile(rx + ("$" if anchored else ""))
