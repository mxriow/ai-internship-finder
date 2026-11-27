from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Posting:
    """A job posting normalised across providers."""
    provider: str
    company: str          # display name from companies.yaml
    token: str            # board token / company id at the provider
    job_id: str
    title: str
    url: str
    locations: list[str] = field(default_factory=list)
    country_codes: list[str] = field(default_factory=list)  # ISO-2 where the feed gives it
    description: str = ""                                    # plain text; archived in data/descriptions/, not in jobs.json
    apply_url: str | None = None
    posted: str | None = None                                # YYYY-MM-DD
    employment_raw: str | None = None                        # provider's own employment type
    department: str | None = None
    language: str | None = None                              # provider-declared language, if any

    @property
    def id(self) -> str:
        return f"{self.provider}:{self.token}:{self.job_id}"


_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(p|div|br|li|ul|ol|h\d|tr)[^>]*>", re.I)
_WS = re.compile(r"[ \t\r\f\v]+")


def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)  # Greenhouse double-escapes content
    s = _BLOCK.sub("\n", s)
    s = _TAG.sub(" ", s)
    s = html.unescape(s)
    s = _WS.sub(" ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def iso_date(value) -> str | None:
    """Accept ISO strings or epoch milliseconds; return YYYY-MM-DD."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except (ValueError, OSError):
        m = re.match(r"\d{4}-\d{2}-\d{2}", str(value))
        return m.group(0) if m else None
