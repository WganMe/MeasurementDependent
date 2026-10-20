#!/usr/bin/env python3
"""Find BibTeX fields not terminated by `,` or `}`.

BibTeX aborts the rest of an entry at such a field, silently discarding every
later field -- including YEAR, which is what broke the PeerJ bibliography.

This scanner skips ALL whitespace (including newlines) when looking for the
character after a field, because the final field of an entry is legitimately
followed by `\n}`. An earlier version skipped only spaces and tabs and reported
every .bib file in the workspace as defective.
"""

from __future__ import annotations

import re
import sys

FIELD = re.compile(
    r"(?im)^[ \t]*(AUTHOR|TITLE|JOURNAL|BOOKTITLE|YEAR|VOLUME|PAGES|"
    r"DOI|URL|PUBLISHER|NUMBER|EDITOR|MONTH|NOTE|SCHOOL|ADDRESS|SERIES|ISBN|ISSN)"
    r"[ \t]*=[ \t]*\{"
)


def scan(text: str) -> list[tuple[int, str]]:
    bad: list[tuple[int, str]] = []
    for m in FIELD.finditer(text):
        brace = m.end() - 1
        depth = 0
        end = -1
        for i in range(brace, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            continue
        j = end + 1
        # skip ALL whitespace, not just spaces and tabs
        while j < len(text) and text[j].isspace():
            j += 1
        if j < len(text) and text[j] not in ",}":
            line = text.count("\n", 0, m.start()) + 1
            bad.append((line, m.group(1).upper()))
    return bad


def main() -> int:
    rc = 0
    for path in sys.argv[1:]:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            print(f"{path}: UNREADABLE ({exc})")
            continue
        bad = scan(text)
        if bad:
            rc = 1
            print(f"{path}: {len(bad)} field(s) missing a terminating comma")
            for line, name in bad[:6]:
                print(f"    line {line}: {name}")
        else:
            print(f"{path}: ok")
    return rc


if __name__ == "__main__":
    sys.exit(main())
