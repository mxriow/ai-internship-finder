"""Polite HTTP client: descriptive User-Agent, per-host rate limit, robots.txt (RFC 9309)."""
from __future__ import annotations

import logging
import threading
import time
from urllib.parse import urlsplit
from .robots import Robots

import requests

log = logging.getLogger(__name__)

DEFAULT_UA = "ch-intern-finder/0.1 (personal internship search; +https://github.com/)"


class RobotsDisallowed(Exception):
    """Raised when robots.txt forbids fetching a URL."""


class FetchError(Exception):
    pass


class PoliteClient:
    def __init__(self, user_agent: str = DEFAULT_UA, max_rps_per_host: float = 2.0,
                 timeout: float = 30.0, retries: int = 2):
        self.user_agent = user_agent
        self.robots_agent = user_agent.split("/")[0].strip()
        self.min_interval = 1.0 / max_rps_per_host
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self._robots: dict[str, Robots | bool] = {}
        self._last: dict[str, float] = {}
        self._host_locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()

    # -- rate limiting -----------------------------------------------------
    def _host_lock(self, host: str) -> threading.Lock:
        with self._lock:
            return self._host_locks.setdefault(host, threading.Lock())

    def _wait(self, host: str, interval: float) -> None:
        last = self._last.get(host, 0.0)
        delay = last + interval - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._last[host] = time.monotonic()

    # -- robots.txt ----------------------------------------------------------
    def _robots_for(self, scheme: str, host: str) -> Robots | bool:
        """Return a parser, or True (allow all) / False (disallow all) per RFC 9309."""
        key = f"{scheme}://{host}"
        if key in self._robots:
            return self._robots[key]
        result: Robots | bool = False
        for attempt in range(2):   # one retry: a single 5xx/timeout should not cost a whole day's data
            try:
                self._wait(host, self.min_interval)
                r = self.session.get(f"{key}/robots.txt", timeout=self.timeout)
            except requests.RequestException as e:
                log.warning("robots.txt unreachable for %s (attempt %d): %s", host, attempt + 1, e)
                result = False      # unreachable: assume complete disallow
            else:
                if 200 <= r.status_code < 300:
                    result = Robots(r.text, self.robots_agent)
                    break
                if 400 <= r.status_code < 500:
                    result = True   # "unavailable": crawler may access anything
                    break
                result = False      # 5xx "unreachable": assume complete disallow
            if attempt == 0:
                time.sleep(3)
        self._robots[key] = result
        return result

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        rules = self._robots_for(parts.scheme, parts.netloc)
        if isinstance(rules, bool):
            return rules
        return rules.allowed(url)

    def _interval(self, url: str) -> float:
        parts = urlsplit(url)
        rules = self._robots.get(f"{parts.scheme}://{parts.netloc}")
        if isinstance(rules, Robots):
            cd = rules.crawl_delay
            if cd:
                return max(self.min_interval, float(cd))
        return self.min_interval

    # -- fetching --------------------------------------------------------------
    def get(self, url: str, params: dict | None = None, ok_404: bool = False,
            headers: dict | None = None) -> requests.Response | None:
        """GET with robots check, rate limiting and retries on 429/5xx/network errors.

        Returns None for a 404 when ok_404 is set; raises FetchError otherwise.
        """
        return self._request("GET", url, params=params, ok_404=ok_404, headers=headers)

    def post_json(self, url: str, payload: dict, ok_404: bool = False, headers: dict | None = None) -> requests.Response | None:
        return self._request("POST", url, json=payload, ok_404=ok_404, headers=headers)

    def _request(self, method: str, url: str, ok_404: bool = False, **kwargs) -> requests.Response | None:
        host = urlsplit(url).netloc
        with self._host_lock(host):
            if not self.allowed(url):
                raise RobotsDisallowed(f"robots.txt disallows {url}")
            interval = self._interval(url)
            for attempt in range(self.retries + 1):
                self._wait(host, interval)
                try:
                    r = self.session.request(method, url, timeout=self.timeout, **kwargs)
                except requests.RequestException as e:
                    err = f"network error: {e}"
                else:
                    if r.status_code == 404 and ok_404:
                        return None
                    if r.status_code < 400:
                        return r
                    err = f"HTTP {r.status_code}"
                    if r.status_code not in (429, 500, 502, 503, 504):
                        break
                if attempt < self.retries:
                    time.sleep(2 ** (attempt + 1))
            raise FetchError(f"{err} for {url}")
