"""Is the daily run healthy? Compares this run's data/last_run.json with the previous one.

Unhealthy when:
  - a workflow step failed (tests, fetch, publish),
  - more than `max_failed_share` of the feeds failed (default 10%), or
  - the number of internships matched dropped by more than `max_drop` vs. the previous run (default 40%).

`python -m finder health --previous PREV.json --current data/last_run.json --outcome tests=success,run=failure`
prints `healthy` or `unhealthy` and writes a Markdown report (the GitHub issue text) to --out.
"""
from __future__ import annotations

import json
from pathlib import Path

MAX_FAILED_SHARE = 0.10
MAX_DROP = 0.40

STEP_HELP = {
    "tests": "The unit tests failed, so the run stopped before fetching. Usually a code or config.yaml change broke a rule.",
    "run": "Fetching or building crashed. The log of the step \"Fetch feeds and rebuild outputs\" shows the error.",
    "publish": "The new data could not be committed or pushed (e.g. a branch protection rule or a conflict).",
    "setup": "Installing Python or the dependencies failed (often a temporary GitHub or PyPI problem; re-run).",
}


def _load(path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")) if path and Path(path).exists() else None
    except (OSError, ValueError):
        return None


def check(previous: dict | None, current: dict | None, outcomes: dict[str, str] | None = None,
          max_failed_share: float = MAX_FAILED_SHARE, max_drop: float = MAX_DROP,
          known_blocked: set[str] | frozenset = frozenset()) -> list[str]:
    """Return the list of problems (empty = healthy).

    Feeds of a provider in `known_blocked` (config.yaml: health.known_blocked_providers) are left out of the
    failed-feeds share and the drop check, so a block already known to the owner does not reopen the issue daily.
    """
    problems = []
    for step, outcome in (outcomes or {}).items():
        if outcome not in ("success", "skipped", ""):
            problems.append(f"Step **{step}** ended with `{outcome}`. {STEP_HELP.get(step, '')}".strip())
    if not current:
        if not problems:
            problems.append("No run summary (data/last_run.json) was produced.")
        return problems
    if previous and previous.get("run_at") and previous.get("run_at") == current.get("run_at") and not problems:
        problems.append("data/last_run.json was not updated by this run.")
    # Feeds vs feeds: `companies` is the number of feeds fetched and `failed` lists one entry per failed feed.
    # (`companies_ok` is not used: it also counts retired feeds that a replacement stands in for.)
    # Failed feeds of a known-blocked provider are set aside on both sides of the ratio.
    n = current.get("companies") or 0
    failed = current.get("failed") or []
    blocked = [f for f in failed if f.get("provider") in known_blocked]
    failed = [f for f in failed if f.get("provider") not in known_blocked]
    n -= len(blocked)
    if n > 0 and len(failed) / n > max_failed_share:
        names = ", ".join(f"{f.get('company')} ({f.get('provider')})" for f in failed[:25])
        problems.append(f"**{len(failed)} of {n} feeds failed** (more than {max_failed_share:.0%}"
                        + (f"; {len(blocked)} known-blocked feeds not counted" if blocked else "") + f"): {names}"
                        + (" …" if len(failed) > 25 else ""))
    def matched(summary):
        if not known_blocked or not summary.get("per_company"):
            return summary.get("matched") or 0
        return sum(c.get("matched") or 0 for c in summary["per_company"] if c.get("provider") not in known_blocked)
    if previous and matched(previous):
        before, now = matched(previous), matched(current)
        if now < before * (1 - max_drop):
            problems.append(f"**Internships dropped from {before} to {now}** ({(before - now) / before:.0%} fewer than the "
                            f"previous run, limit {max_drop:.0%}). Often one big employer's feed broke or changed format.")
    return problems


def report(problems: list[str], current: dict | None, run_url: str = "") -> str:
    lines = ["The daily internship update needs attention.", ""]
    lines += [f"- {p}" for p in problems]
    if current:
        lines += ["", f"Run at {current.get('run_at')}: {current.get('companies_ok')}/{current.get('companies')} feeds ok, "
                      f"{current.get('matched')} internships matched, {current.get('new')} new."]
        failed = current.get("failed") or []
        if failed:
            lines += ["", "<details><summary>Failed feeds</summary>", ""]
            lines += [f"- {f.get('company')} ({f.get('provider')}): {str(f.get('error'))[:200]}" for f in failed]
            lines += ["", "</details>"]
    if run_url:
        lines += ["", f"Run log: {run_url}"]
    lines += ["", "See the README section *Troubleshooting* for what each problem means and what you can do. "
                  "This issue closes itself after the next healthy run."]
    return "\n".join(lines) + "\n"


def main(args) -> int:
    outcomes = dict(x.split("=", 1) for x in (args.outcome or "").split(",") if "=" in x)
    prev, cur = _load(args.previous), _load(args.current)
    blocked = set()
    try:
        import yaml
        cfg = yaml.safe_load((Path(__file__).resolve().parent.parent / "config.yaml").read_text(encoding="utf-8")) or {}
        blocked = set((cfg.get("health") or {}).get("known_blocked_providers") or [])
    except Exception:  # noqa: BLE001 - a config problem must not hide a real failure
        blocked = set()
    problems = check(prev, cur, outcomes, known_blocked=blocked)
    if args.out:
        Path(args.out).write_text(report(problems, cur, args.run_url or ""), encoding="utf-8")
    print("unhealthy" if problems else "healthy")
    return 0
