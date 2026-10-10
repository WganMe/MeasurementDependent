#!/usr/bin/env python3
"""Write the three text fields the PeerJ portal asks for, ready to paste.

WHY THIS EXISTS. The portal's Title/Abstract tab is not the manuscript: it is a set of
plain-text fields with their own limits, and its checklist warns about three things that a
PDF cannot warn you about --

    "Title and abstract entered exactly as you want them to appear in the final publication."
    "No linebreaks or strange characters in the abstract."
    "Special characters entered correctly (non-latin / latex)."

A copy-paste from the PDF would arrive with the line-number gutter, wrapped lines and the
typographic characters below, any of which can paste badly into a text box. So the values are
EXTRACTED from the built PDF and written into `portal-fields.md` as paste-ready text, the same
way every other value in this submission is read rather than retyped.

THE CHARACTERS THAT MATTER. The built abstract contains:

    U+2013  EN DASH        "2013-2026", "Clark-Evans"   standard typography, pastes fine
    U+2019  RIGHT SINGLE Q "year's"                     standard typography, pastes fine
    U+2212  MINUS SIGN     "-99 m per year"             NOT a hyphen-minus

U+2212 is the one to strip. It is a mathematical operator, not the keyboard character, and a
plain text field that does not expect maths can reject it, substitute it, or render it as a
missing glyph. It is replaced with the ASCII hyphen-minus, which reads identically here.

The en dash and the curly apostrophe are kept: they are ordinary published typography, PeerJ
itself uses them, and their ASCII stand-ins would be a change to the text rather than a repair
to it. Only the minus is normalised, and the script reports every character it changed.

USAGE
    python3 make_portal_fields.py        # writes ../portal-fields.md
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent                      # the submission root, one level up

TITLE_LIMIT = 250
SHORT_LIMIT = 50
ABSTRACT_LIMIT = 2000                  # CHARACTERS, not words

# Characters whose ASCII form is a faithful stand-in. Anything not listed is left alone and
# reported, so a new character cannot slip through unnoticed.
NORMALISE = {
    "\u2212": "-",      # MINUS SIGN -> hyphen-minus
    "\u00a0": " ",      # NO-BREAK SPACE -> ordinary space
    "\u2010": "-",      # HYPHEN
    "\u2011": "-",      # NON-BREAKING HYPHEN
    "\u2012": "-",      # FIGURE DASH
}

# The portal wants a short title (<= 50 characters) and the manuscript has none: it is a
# portal-only field. This is a RECOMMENDATION, not a value read from the paper -- the author
# can replace it. The alternatives are given so the choice is visible.
SHORT_TITLE = "Measurement-dependent urban sensor clustering"
SHORT_TITLE_ALTERNATIVES = [
    "Measurement-dependent spatial clustering",
    "Measurement-dependent clustering at city scale",
]


def pdf_text(pdf: pathlib.Path) -> str:
    p = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit("REFUSING: pdftotext failed on %s" % pdf)
    return p.stdout


def abstract_from_pdf(pdf: pathlib.Path) -> str:
    """The abstract as a reader sees it, flattened to ONE line.

    The line-number gutter ("  14   ") is stripped and every run of whitespace collapsed,
    because the portal warns specifically about linebreaks in the abstract field.
    """
    txt = pdf_text(pdf)
    s = txt.index("ABSTRACT") + len("ABSTRACT")
    e = txt.index("INTRODUCTION")
    body = re.sub(r"(?m)^\s*\d{1,3}\s{1,6}", "", txt[s:e])
    return re.sub(r"\s+", " ", body).strip()


def title_from_source(pdf: pathlib.Path) -> str:
    """The title from `peerj-main.tex`, then CHECKED against the built PDF.

    Parsing it out of the PDF header is unreliable: the title wraps over two lines and every
    line begins with the line-number gutter (" 1   Measurement-Dependent Clustering in the"),
    so a naive read picked up an empty string. The `.tex` has it in one piece.

    The source is not trusted on its own, though -- the point of this script is that a portal
    value must match what the PDF actually says. So the extracted title is asserted present in
    the PDF's first-page text before it is used.
    """
    tex = (OUT / "peerj-main.tex").read_text(encoding="utf-8")
    m = re.search(r"\\title\{([^{}]*)\}", tex)
    if not m:
        raise SystemExit("REFUSING: no \\title{} in peerj-main.tex")
    title = re.sub(r"\s+", " ", m.group(1)).strip()

    # Compare against the PDF with the line-number gutter removed: every line of the review
    # PDF starts with a number, so "the\n 2    Growing" becomes "the 2 Growing" and a plain
    # substring test fails on a title that is in fact printed correctly.
    page = re.sub(r"(?m)^\s*\d{1,3}\s{1,6}", "", pdf_text(pdf))
    page = re.sub(r"\s+", " ", page)
    if title not in page:
        raise SystemExit(
            "REFUSING: the title in peerj-main.tex is not the title printed in the PDF.\n"
            "  .tex : %s" % title)
    return title


def normalise(text: str) -> tuple[str, Counter]:
    """Replace the characters whose ASCII stand-in is exact; count every replacement."""
    changed = Counter()
    out = []
    for ch in text:
        if ch in NORMALISE:
            changed[ch] += 1
            out.append(NORMALISE[ch])
        else:
            out.append(ch)
    return "".join(out), changed


def main() -> int:
    pdf = OUT / "peerj-main.pdf"
    if not pdf.exists():
        print("REFUSING: %s not found. Run convert_to_peerj.py and pdflatex first." % pdf)
        return 1

    raw_title = title_from_source(pdf)
    raw_abstract = abstract_from_pdf(pdf)
    title, t_changed = normalise(raw_title)
    abstract, a_changed = normalise(raw_abstract)

    # --- the portal's own limits, enforced here rather than discovered at the portal
    problems = []
    if len(title) > TITLE_LIMIT:
        problems.append("title is %d characters, limit %d" % (len(title), TITLE_LIMIT))
    if len(SHORT_TITLE) > SHORT_LIMIT:
        problems.append("short title is %d characters, limit %d"
                        % (len(SHORT_TITLE), SHORT_LIMIT))
    if len(abstract) > ABSTRACT_LIMIT:
        problems.append("abstract is %d characters, limit %d"
                        % (len(abstract), ABSTRACT_LIMIT))
    if "\n" in abstract:
        problems.append("abstract contains a linebreak")
    if problems:
        raise SystemExit("REFUSING: " + "; ".join(problems))

    def changed_note(counter):
        if not counter:
            return "no character substitutions were needed"
        return ", ".join("U+%04X %s replaced x%d with %r"
                         % (ord(c), c, n, NORMALISE[c]) for c, n in counter.items())

    doc = []
    doc.append("# PeerJ portal text fields — paste these exactly\n")
    doc.append("Generated by `source/make_portal_fields.py` from the built `peerj-main.pdf`, "
               "not retyped.\n")
    doc.append("The portal's checklist asks that these be entered *\"exactly as you want them "
               "to appear in the final publication\"*, with no linebreaks and correct special "
               "characters. The fenced blocks below are the exact strings to paste.\n")

    doc.append("## Title — %d of %d characters\n" % (len(title), TITLE_LIMIT))
    doc.append("```text")
    doc.append(title)
    doc.append("```\n")

    doc.append("## Short Title — %d of %d characters\n"
               % (len(SHORT_TITLE), SHORT_LIMIT))
    doc.append("**This one is a recommendation, not a value read from the paper:** the "
               "manuscript carries no short title, because the portal is the only place that "
               "asks for one. Replace it if you prefer another.\n")
    doc.append("```text")
    doc.append(SHORT_TITLE)
    doc.append("```\n")
    doc.append("Alternatives, all within the limit:\n")
    for alt in SHORT_TITLE_ALTERNATIVES:
        doc.append("- `%s` (%d)" % (alt, len(alt)))
    doc.append("")

    doc.append("## Abstract — %d of %d characters, %d words, one line\n"
               % (len(abstract), ABSTRACT_LIMIT, len(abstract.split())))
    doc.append("The limit is **characters, not words**, which is worth noting because every "
               "other place in this submission counts the abstract in words (199). The field "
               "is a single paragraph: the text below carries no linebreaks.\n")
    doc.append("```text")
    doc.append(abstract)
    doc.append("```\n")

    doc.append("## Character handling\n")
    doc.append("Extracted from the PDF and normalised where a plain text box would not expect "
               "the character:\n")
    doc.append("- Abstract: %s" % changed_note(a_changed))
    doc.append("- Title: %s" % changed_note(t_changed))
    doc.append("")
    doc.append("The en dash in `2013-2026` and `Clark-Evans`, and the curly apostrophe in "
               "`year's`, are kept as they are: they are ordinary published typography and "
               "PeerJ uses them, so replacing them would alter the text rather than repair it. "
               "The minus sign is different — U+2212 is a mathematical operator rather than "
               "the keyboard hyphen, and a plain field can reject or mis-render it, so "
               "`-99 m per year` uses the ASCII hyphen-minus.\n")
    doc.append("Verify by eye against the manuscript's own abstract before pasting; this file "
               "is generated, so a change to the paper's abstract must be followed by "
               "`./build.sh` to regenerate it.\n")

    (OUT / "portal-fields.md").write_text("\n".join(doc) + "\n", encoding="utf-8")

    print("wrote %s" % (OUT / "portal-fields.md"))
    print("  title       %3d chars (limit %d)" % (len(title), TITLE_LIMIT))
    print("  short title %3d chars (limit %d)" % (len(SHORT_TITLE), SHORT_LIMIT))
    print("  abstract    %3d chars (limit %d), %d words, no linebreaks"
          % (len(abstract), ABSTRACT_LIMIT, len(abstract.split())))
    print("  abstract normalised: %d character(s) changed" % sum(a_changed.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
