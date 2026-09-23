"""Shared, cached builds of the generated site for the page tests (one build per variant per test run).

    from pagebuild import build, html_of, main_text, PageParser
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
SCRIPT = ROOT / "scripts" / "build_pages.py"
TODAY = "2026-09-23"
_cache = {}


def build(variant="default"):
    """variant: 'default' | 'ads' (tests/fixtures/site-ads.json) | 'snapshot' (tests/fixtures/pets-board.json)."""
    if variant in _cache:
        return _cache[variant]
    out = Path(tempfile.mkdtemp(prefix=f"nkpages-{variant}-"))
    args = [sys.executable, str(SCRIPT), "--today", TODAY, "--out", str(out)]
    if variant == "ads":
        args += ["--config", str(FIX / "site-ads.json")]
    if variant == "snapshot":
        args += ["--snapshot", "--board", str(FIX / "pets-board.json")]
    if os.environ.get("NK_KEEP_GOING"):
        args += ["--keep-going"]  # while pages are being written: build what exists
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"build_pages.py failed ({variant}):\n{r.stdout}\n{r.stderr}")
    _cache[variant] = out
    return out


def files(out, pattern="**/*.html"):
    return sorted(p for p in out.glob(pattern) if not p.is_symlink())


def html_of(out, route):
    p = out / ("404.html" if route == "/404.html" else route.lstrip("/") + "index.html")
    return p.read_text(encoding="utf-8")


class PageParser(HTMLParser):
    """Collects the visible text of <main> (no script/style/template/[hidden]), headings, links and attributes."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.main_text, self.all_text = [], [], []
        self.h1 = []
        self.links, self.srcs, self.tags = [], [], []
        self._skip = 0
        self._in_main = 0
        self._h1 = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        if tag in ("a", "link") and a.get("href"):
            self.links.append(a["href"])
        if tag in ("img", "script", "source", "iframe") and (a.get("src") or a.get("srcset")):
            self.srcs.append(a.get("src") or a.get("srcset"))
        if tag in self.VOID:
            return
        hidden = "hidden" in a or tag in ("script", "style", "template", "noscript")
        self.stack.append((tag, hidden))
        if hidden:
            self._skip += 1
        if tag == "main":
            self._in_main += 1
        if tag == "h1":
            self._h1 += 1
            self.h1.append("")

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        while self.stack:
            t, hidden = self.stack.pop()
            if hidden:
                self._skip -= 1
            if t == "main":
                self._in_main -= 1
            if t == "h1":
                self._h1 -= 1
            if t == tag:
                break

    def handle_data(self, d):
        if self._skip:
            return
        self.all_text.append(d)
        if self._in_main:
            self.main_text.append(d)
        if self._h1:
            self.h1[-1] += d


def parse(text):
    p = PageParser()
    p.feed(text)
    return p


def words(s):
    return len(re.findall(r"[A-Za-z0-9][\w'’.-]*", s))


def main_words(text):
    return words(" ".join(parse(text).main_text))
