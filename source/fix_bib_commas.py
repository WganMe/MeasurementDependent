#!/usr/bin/env python3
"""Repair BibTeX entries whose TITLE field is missing its trailing comma.

BibTeX aborts the rest of an entry when a field is not followed by `,` or `}`.
In this database every entry's TITLE lost its comma, so YEAR (and anything
after it) was silently discarded.  apalike then emitted
`\\bibitem[Author et al., ]{key}` with an empty year, and natbib rejected the
bibliography as "not compatible with author-year citations".

The repair locates the TITLE field's *matching* closing brace (some titles wrap
across lines and some contain nested braces such as {SQL}), then inserts a comma
if the next non-whitespace character is not already `,` or `}`.

Run with --check to report without writing.
"""

from __future__ import annotations

import argparse
import re
import sys


def find_field_end(text: str, start: int) -> int:
    """Return the index of the brace matching the one at *start*."""
    assert text[start] == "{"
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unbalanced braces")


def repair(text: str) -> tuple[str, list[tuple[str, int]]]:
    """Insert missing commas after TITLE fields. Returns (text, fixes)."""
    fixes: list[tuple[str, int]] = []
    out = []
    pos = 0
    for m in re.finditer(r"(?im)^[ \t]*TITLE[ \t]*=[ \t]*\{", text):
        brace = m.end() - 1
        if brace < pos:
            continue
        try:
            end = find_field_end(text, brace)
        except ValueError:
            continue
        after = end + 1
        # find next non-space character
        nxt = after
        while nxt < len(text) and text[nxt] in " \t":
            nxt += 1
        if nxt < len(text) and text[nxt] in ",}":
            continue  # already well formed
        # describe the entry for the report: nearest preceding @type{key,
        at = text.rfind("@", 0, m.start())
        key = "?"
        if at != -1:
            head = re.match(r"@\w+\s*\{\s*([^,\s]+)\s*,", text[at:])
            if head:
                key = head.group(1)
        line = text.count("\n", 0, end) + 1
        fixes.append((key, line))
        out.append(text[pos : end + 1])
        out.append(",")
        pos = end + 1
    out.append(text[pos:])
    return "".join(out), fixes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bib", nargs="?", default="references.bib")
    ap.add_argument("--check", action="store_true", help="report only")
    args = ap.parse_args()

    with open(args.bib, encoding="utf-8") as fh:
        original = fh.read()

    fixed, fixes = repair(original)

    if not fixes:
        print(f"{args.bib}: no missing TITLE commas found")
        return 0

    for key, line in fixes:
        print(f"  {key}: TITLE comma restored (line {line})")
    print(f"{len(fixes)} entries repaired")

    if args.check:
        return 1

    with open(args.bib, "w", encoding="utf-8") as fh:
        fh.write(fixed)
    print(f"wrote {args.bib}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
