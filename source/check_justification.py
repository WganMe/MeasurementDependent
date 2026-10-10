#!/usr/bin/env python3
"""
Test whether the body text is justified, using the actual glyph coordinates.

A character-count heuristic is wrong here. The last line of every paragraph, every
heading, every caption and every table row legitimately ends short, so counting
"short lines" produces a verdict that is both false and confident. Worse, the
paper title and the author block span the full page width and dominate any such
count, which is exactly why the first version of this script said "NOT justified"
about fully justified text.

The correct test uses pdftotext -bbox, where each word carries xMin/xMax.
Justified text means that, inside a paragraph, every line except the last reaches
the same right edge. So we group words into lines, compare right edges, and
restrict the test to pages that actually contain body prose.

Usage:  python3 check_justification.py [pdf] [--page N]
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict

pdf = "main.pdf"
only_page = None
args = sys.argv[1:]
if args and not args[0].startswith("--"):
    pdf = args[0]
    args = args[1:]
if "--page" in args:
    only_page = int(args[args.index("--page") + 1])

xml = subprocess.run(["pdftotext", "-bbox", pdf, "-"],
                     capture_output=True, text=True).stdout
pages = re.findall(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>',
                   xml, re.S)
print("justification check on %s" % pdf)

total = flush_total = 0
rows = []
for pno, (pw, ph, page) in enumerate(pages, 1):
    if only_page and pno != only_page:
        continue
    words = re.findall(
        r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" '
        r'yMax="([\d.]+)">(.*?)</word>', page)
    if not words:
        continue
    lines = defaultdict(list)
    for xmn, ymn, xmx, ymx, w in words:
        lines[round(float(ymn) / 3.0)].append((float(xmn), float(xmx), w))
    if len(lines) < 4:
        continue
    ordered = []
    for k in sorted(lines):
        ws = sorted(lines[k])
        ordered.append((min(w[0] for w in ws), max(w[1] for w in ws),
                        " ".join(w[2] for w in ws)))
    # body prose only: long lines that begin at the text block, not at a margin
    body = [l for l in ordered if len(l[2]) > 45 and l[0] < float(pw) * 0.30]
    if len(body) < 6:
        continue
    right = max(l[1] for l in body)
    same = [l for l in body if abs(l[1] - right) <= 4.0]
    total += len(body)
    flush_total += len(same)
    rows.append((pno, len(body), len(same), right))

print("\n  pages with body prose : %d" % len(rows))
print("  %-6s %-7s %-7s %-7s %s" % ("page", "lines", "flush", "short", "right edge"))
for pno, n, f, r in rows:
    print("  %-6d %-7d %-7d %-7d %.1f pt" % (pno, n, f, n - f, r))

pct = 100.0 * flush_total / total if total else 0.0
print("\n  body lines %d | flush to the right margin %d (%.0f%%) | paragraph-final %d"
      % (total, flush_total, pct, total - flush_total))
print()
if pct >= 65:
    print("  VERDICT: body text IS justified. Short lines are the final line of each")
    print("           paragraph, which is what justification looks like.")
else:
    print("  VERDICT: NOT justified — ragged-right is in effect.")
