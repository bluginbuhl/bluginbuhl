#!/usr/bin/env python3
"""Render GitHub profile stats to static SVG cards.

Queries the GitHub GraphQL API and writes `assets/stats-dark.svg` and
`assets/stats-light.svg`. The README embeds those local files, so the card
keeps rendering even when third-party stats services go down.

Deliberately reports activity counts only. Language proficiency is curated by
hand in the README -- repo byte counts measure what happened to get committed,
not what anyone is actually good at.

Stdlib only, so the workflow needs no dependency install step.

Usage:
    GITHUB_TOKEN=$(gh auth token) python3 scripts/generate_stats.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

LOGIN = os.environ.get("STATS_LOGIN", "bluginbuhl")
OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "assets"

QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes { stargazerCount }
    }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
    }
  }
}
"""

THEMES = {
    "dark": {
        "bg": "#0d1117",
        "border": "#30363d",
        "text": "#e6edf3",
        "muted": "#8b949e",
        "accent": "#58a6ff",
    },
    "light": {
        "bg": "#ffffff",
        "border": "#d0d7de",
        "text": "#1f2328",
        "muted": "#59636e",
        "accent": "#0969da",
    },
}

FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,"
    "'Liberation Sans',sans-serif"
)

WIDTH = 840
HEIGHT = 162
PAD = 28


def fetch(token: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{LOGIN}-profile-stats",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise SystemExit(f"GraphQL errors: {json.dumps(payload['errors'], indent=2)}")
    return payload["data"]["user"]


def summarize(user: dict) -> list[tuple[str, str]]:
    stars = sum(r["stargazerCount"] for r in user["repositories"]["nodes"])

    contrib = user["contributionsCollection"]
    # restrictedContributionsCount covers private work, and is only non-zero when
    # the token has been granted visibility into it.
    commits = contrib["totalCommitContributions"] + contrib["restrictedContributionsCount"]

    return [
        # totalCount is already filtered to public non-forks by the query.
        (f"{user['repositories']['totalCount']}", "source repos"),
        (f"{stars}", "stars earned"),
        (f"{commits}", "commits / yr"),
        # No PR metric: totalPullRequestContributions counts public PRs only,
        # with no restricted-contributions counterpart the way commits have. On
        # a profile whose work is mostly in private org repos it reads as a
        # single digit and badly understates reality.
        (f"{user['followers']['totalCount']}", "followers"),
    ]


def render(metrics: list[tuple[str, str]], theme: dict, updated: str) -> str:
    c = theme
    parts: list[str] = []
    add = parts.append

    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
        f'aria-label="GitHub activity for {escape(LOGIN)}">'
    )
    add(
        f"<style>text{{font-family:{FONT}}}"
        f".h{{font-size:13px;font-weight:600;letter-spacing:.10em;fill:{c['muted']}}}"
        f".n{{font-size:34px;font-weight:700;fill:{c['text']}}}"
        f".l{{font-size:11px;font-weight:500;letter-spacing:.06em;fill:{c['muted']}}}"
        f".m{{font-size:11px;fill:{c['muted']}}}</style>"
    )

    add(
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="12" '
        f'fill="{c["bg"]}" stroke="{c["border"]}"/>'
    )
    # Accent keyline along the top edge, clipped to the card's rounded corners.
    add(f'<clipPath id="card"><rect width="{WIDTH}" height="{HEIGHT}" rx="12"/></clipPath>')
    add(f'<rect width="{WIDTH}" height="3" fill="{c["accent"]}" clip-path="url(#card)"/>')

    # Identifies the card when viewed standalone; the README section already
    # supplies the "GitHub activity" heading, so don't repeat it here.
    add(f'<text x="{PAD}" y="40" class="h">@{escape(LOGIN.upper())}</text>')
    add(
        f'<text x="{WIDTH - PAD}" y="40" class="m" text-anchor="end">'
        f"updated {escape(updated)}</text>"
    )
    add(f'<line x1="{PAD}" y1="58" x2="{WIDTH - PAD}" y2="58" stroke="{c["border"]}"/>')

    span = (WIDTH - 2 * PAD) / len(metrics)
    for i, (value, label) in enumerate(metrics):
        cx = PAD + span * i + span / 2
        add(f'<text x="{cx:.1f}" y="112" class="n" text-anchor="middle">{escape(value)}</text>')
        add(
            f'<text x="{cx:.1f}" y="133" class="l" text-anchor="middle">'
            f"{escape(label.upper())}</text>"
        )
        if i:
            x = PAD + span * i
            add(f'<line x1="{x:.1f}" y1="80" x2="{x:.1f}" y2="140" stroke="{c["border"]}"/>')

    add("</svg>")
    return "".join(parts)


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("GITHUB_TOKEN is not set", file=sys.stderr)
        return 1

    try:
        user = fetch(token)
    except urllib.error.HTTPError as err:
        print(f"GitHub API {err.code}: {err.read().decode()[:400]}", file=sys.stderr)
        return 1

    metrics = summarize(user)
    updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    OUT_DIR.mkdir(exist_ok=True)
    for name, theme in THEMES.items():
        path = OUT_DIR / f"stats-{name}.svg"
        path.write_text(render(metrics, theme, updated) + "\n")
        print(f"wrote {path.relative_to(OUT_DIR.parent)}")

    print("  " + " | ".join(f"{v} {l}" for v, l in metrics))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
