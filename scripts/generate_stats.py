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

# Hand-maintained language mix.
#
# Not derived from repo bytes on purpose. Public repos hold 12 of ~700 commits
# a year and contain no TypeScript at all, so anything measured from them
# describes a rounding error rather than the actual work. Byte counts are also
# a poor proxy for effort: one asset-heavy web repo outweighed a dozen Python
# ones when this was computed automatically.
#
# Weights are relative and normalized before rendering, so they need not sum to
# 100. Adjust them when the balance shifts.
LANGUAGE_MIX = [
    ("Python", 45, "#3572A5"),
    ("TypeScript", 25, "#3178C6"),
    ("Shell", 8, "#89E051"),
    ("Jupyter", 7, "#DA5B0B"),
    ("JavaScript", 7, "#F1E05A"),
    ("HTML / CSS", 5, "#E34C26"),
    ("Other", 3, "#6E7681"),
]

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
        "track": "#21262d",
    },
    "light": {
        "bg": "#ffffff",
        "border": "#d0d7de",
        "text": "#1f2328",
        "muted": "#59636e",
        "accent": "#0969da",
        "track": "#eaeef2",
    },
}

FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,"
    "'Liberation Sans',sans-serif"
)

WIDTH = 840
HEIGHT = 248
PAD = 28


def normalized_mix() -> list[tuple[str, float, str]]:
    """Language mix as percentages, so the declared weights can be arbitrary."""
    total = sum(weight for _, weight, _ in LANGUAGE_MIX)
    if total <= 0:
        raise SystemExit("LANGUAGE_MIX weights must sum to a positive number")
    return [(name, weight / total * 100, color) for name, weight, color in LANGUAGE_MIX]


def text_width(s: str, size: float) -> float:
    """Rough advance-width estimate for the sans stack above."""
    return len(s) * size * 0.55


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


def render(
    metrics: list[tuple[str, str]],
    langs: list[tuple[str, float, str]],
    theme: dict,
    updated: str,
) -> str:
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
        f".g{{font-size:11px;font-weight:500;fill:{c['text']}}}"
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

    add(f'<line x1="{PAD}" y1="162" x2="{WIDTH - PAD}" y2="162" stroke="{c["border"]}"/>')
    add(f'<text x="{PAD}" y="188" class="h">LANGUAGE MIX</text>')
    add(
        f'<text x="{WIDTH - PAD}" y="188" class="m" text-anchor="end">'
        f"including private work</text>"
    )

    # Stacked bar, rounded via a clip so the segments square up inside it.
    bar_y, bar_h, bar_w = 200, 10, WIDTH - 2 * PAD
    add(
        f'<clipPath id="bar"><rect x="{PAD}" y="{bar_y}" width="{bar_w}" '
        f'height="{bar_h}" rx="5"/></clipPath>'
    )
    add(
        f'<rect x="{PAD}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="5" '
        f'fill="{c["track"]}"/>'
    )
    # Segments are inset by a hairline gap so neighbours stay distinguishable
    # even when their Linguist colors are close. Python and TypeScript are both
    # blue, and butted together they read as one bar.
    gap = 2.0
    last = len(langs) - 1
    x = float(PAD)
    for i, (_, pct, color) in enumerate(langs):
        w = bar_w * pct / 100
        # The final segment runs the full width so it reaches the bar's right
        # edge. Inset it like the others and the rounded track shows through,
        # giving the two ends visibly different caps.
        seg = w if i == last else max(w - gap, 1.0)
        add(
            f'<rect x="{x:.2f}" y="{bar_y}" width="{seg:.2f}" '
            f'height="{bar_h}" fill="{color}" clip-path="url(#bar)"/>'
        )
        x += w

    lx = float(PAD)
    for name, pct, color in langs:
        label = f"{name} {pct:.0f}%"
        add(f'<circle cx="{lx + 4:.1f}" cy="230" r="4" fill="{color}"/>')
        add(f'<text x="{lx + 14:.1f}" y="234" class="g">{escape(label)}</text>')
        lx += 14 + text_width(label, 11) + 20

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
    langs = normalized_mix()
    updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    OUT_DIR.mkdir(exist_ok=True)
    for name, theme in THEMES.items():
        path = OUT_DIR / f"stats-{name}.svg"
        path.write_text(render(metrics, langs, theme, updated) + "\n")
        print(f"wrote {path.relative_to(OUT_DIR.parent)}")

    print("  " + " | ".join(f"{v} {l}" for v, l in metrics))
    print("  " + ", ".join(f"{n} {p:.0f}%" for n, p, _ in langs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
