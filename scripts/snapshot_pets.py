#!/usr/bin/env python3
"""Snapshot the open lost & found pet listings for the deploy build (CI only, standard library only).

    python scripts/snapshot_pets.py                          # GitHub API -> site/data/pets-board.json
    python scripts/snapshot_pets.py --issues tests/fixtures/pet_issues.json --fetched 2026-09-23T13:15:00Z \\
        --out tests/fixtures/pets-board.json                 # the test fixture, from saved issues

Reads the repo's open issues (GITHUB_TOKEN as a bearer token when set, up to 5 pages of 100), keeps the ones made
with the lost-found-pet form, and runs each through nkpages.pets.parse_issue, sanitize and geocode_near, the same
code pets.js runs in the browser. Writes {"fetched": ISO UTC, "posts": [...]}. The file is never committed.

This must never fail a deploy: on any error it prints a warning and exits 0 without writing, and the site then
falls back to the live GitHub API (and says so honestly when that fails too).
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nkpages import data as ND  # noqa: E402
from nkpages import pets as P  # noqa: E402

API = "https://api.github.com/repos/{repo}/issues?state=open&per_page=100&page={page}"
PAGES = 5


def fetch_issues(repo, token=None, pages=PAGES):
    out = []
    for page in range(1, pages + 1):
        req = urllib.request.Request(API.format(repo=repo, page=page), headers={
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nk15068-snapshot"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=30) as r:
            batch = json.loads(r.read().decode("utf-8"))
        if not isinstance(batch, list):
            raise ValueError("GitHub answered with something other than a list of issues")
        out += batch
        if len(batch) < 100:
            break
    return out


def board(issues, repo, fetched, site=ND.SITE):
    """{"fetched", "posts"} from raw issues, geocoded against the site's road and street data."""
    data = site / "data"
    D = {"meta": ND.read_json(data / "meta.json"), "roads": ND.read_json(data / "roads.json")}
    idx = P.build_index(ND.lines(D))
    streets = ND.read_json(data / "streets.json", [])
    return {"fetched": fetched, "posts": P.snapshot_posts(issues, idx, streets, repo)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--issues", help="read issues from this JSON file instead of the GitHub API")
    ap.add_argument("--out", default=str(ND.SITE / "data" / "pets-board.json"))
    ap.add_argument("--fetched", help="ISO UTC time to record (default: now)")
    ap.add_argument("--repo", default=None, help="owner/name (default: data/site.json repo, else GITHUB_REPOSITORY)")
    a = ap.parse_args(argv)
    try:
        cfg = ND.read_json(ND.ROOT / "data" / "site.json", {}) or {}
        repo = a.repo or cfg.get("repo") or os.environ.get("GITHUB_REPOSITORY") or P.REPO
        fetched = a.fetched or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if a.issues:
            issues = json.loads(Path(a.issues).read_text(encoding="utf-8"))
        else:
            issues = fetch_issues(repo, os.environ.get("GITHUB_TOKEN"))
        snap = board(issues, repo, fetched)
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snap, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"snapshot_pets: {len(snap['posts'])} open listing(s) from {len(issues)} issue(s) -> {out}")
    except Exception as e:  # never fail the deploy
        print(f"::warning::snapshot_pets: no snapshot written ({type(e).__name__}: {e}); "
              "the board will read the GitHub API live", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
