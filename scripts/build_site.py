"""Build the static website from the standalone decision page.

Usage: .venv/bin/python scripts/build_site.py [OUT_DIR]   (default ../blockwise-site)

Writes OUT_DIR/index.html (title and meta in <head>, no tool-specific tags) and OUT_DIR/.nojekyll.
Run `python -m invopt.cli page` first so the standalone page is current.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "out" / "blockwise_standalone.html"
TITLE = "Blockwise · risk-aware inventory planner"
DESC = ("Which hotel rooms and flight seats to lock in, how many, and under which contract, within a budget. "
        "Tested on real bookings and 15 years of official Singapore data.")


def build(out_dir: Path) -> Path:
    html = SRC.read_text()
    html = re.sub(r'<meta name="claude:[^"]*" content="[^"]*">\n?', "", html)
    # the template opens with <title> and font <link>s before its <style>: move them into <head>
    body_start = html.index("<body>") + len("<body>")
    style_at = html.index("<style>", body_start)
    lead = re.sub(r"<title>.*?</title>\n?", "", html[body_start:style_at], flags=re.S).strip()
    html = html[:body_start] + "\n" + html[style_at:]
    head = (f"<title>{TITLE}</title>\n<meta name=\"description\" content=\"{DESC}\">\n"
            f"<meta property=\"og:title\" content=\"{TITLE}\">\n<meta property=\"og:description\" content=\"{DESC}\">\n"
            f"<meta name=\"theme-color\" content=\"#0a0b0d\">\n{lead}\n</head>")
    assert html.count("</head>") == 1, "expected one </head> in the standalone page"
    html = html.replace("</head>", head, 1)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html)
    (out_dir / ".nojekyll").write_text("")
    return out_dir / "index.html"


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "blockwise-site"
    p = build(out)
    print(f"wrote {p} ({p.stat().st_size / 1e6:.2f} MB)")
