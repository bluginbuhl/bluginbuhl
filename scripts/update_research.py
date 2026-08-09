#!/usr/bin/env python3
"""Refresh the citation metrics line in README.md.

Reads from OpenAlex rather than Google Scholar. Scholar has no API, forbids
scraping in its terms, and reliably serves a CAPTCHA to datacenter IPs like
GitHub Actions runners -- a scraper would pass locally and then quietly rot in
CI. OpenAlex is open, keyless, and stable from a runner.

The tradeoff is coverage: OpenAlex indexes somewhat fewer citing works than
Scholar, so its totals run lower. The line it writes is labelled OpenAlex so
the number always matches its stated source.

Rewrites only the text between the RESEARCH_STATS markers in README.md.

Usage:
    python3 scripts/update_research.py
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# OpenAlex author ID. Resolve a new one with:
#   curl 'https://api.openalex.org/authors?search=NAME'
AUTHOR_ID = "A5088330543"

# OpenAlex asks API users to identify themselves; doing so also grants access
# to their faster "polite pool".
MAILTO = "ben.luginbuhl@gmail.com"

SCHOLAR_URL = "https://scholar.google.com/citations?user=lAqY7oIAAAAJ&hl=en"

README = pathlib.Path(__file__).resolve().parent.parent / "README.md"
START = "<!-- RESEARCH_STATS:start -->"
END = "<!-- RESEARCH_STATS:end -->"


def fetch() -> dict:
    url = f"https://api.openalex.org/authors/{AUTHOR_ID}?mailto={urllib.parse.quote(MAILTO)}"
    req = urllib.request.Request(url, headers={"User-Agent": f"profile-readme ({MAILTO})"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def build_line(author: dict) -> str:
    stats = author.get("summary_stats") or {}
    citations = author.get("cited_by_count")
    h_index = stats.get("h_index")
    works = author.get("works_count")

    if citations is None or h_index is None:
        raise SystemExit("OpenAlex response missing citation metrics")

    updated = dt.datetime.now(dt.timezone.utc).strftime("%b %Y")
    return (
        f"[**Google Scholar**]({SCHOLAR_URL}) · "
        f"{citations:,} citations · h-index {h_index} · {works} indexed works "
        f"<br/><sub>Metrics via [OpenAlex](https://openalex.org/), refreshed {updated}. "
        f"Scholar reports higher totals because it indexes more citing sources.</sub>"
    )


def main() -> int:
    try:
        author = fetch()
    except urllib.error.HTTPError as err:
        print(f"OpenAlex {err.code}: {err.read().decode()[:300]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as err:
        print(f"OpenAlex unreachable: {err.reason}", file=sys.stderr)
        return 1

    line = build_line(author)
    text = README.read_text()

    pattern = re.compile(
        re.escape(START) + r".*?" + re.escape(END),
        re.DOTALL,
    )
    if not pattern.search(text):
        print(f"Markers {START} / {END} not found in README.md", file=sys.stderr)
        return 1

    updated = pattern.sub(f"{START}\n{line}\n{END}", text)
    if updated == text:
        print("Research metrics unchanged.")
        return 0

    README.write_text(updated)
    print(f"Updated: {line.splitlines()[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
