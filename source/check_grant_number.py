#!/usr/bin/env python3
"""Check the UQU grant number before the manuscript is submitted or released.

WHY THIS EXISTS. Umm Al-Qura University's Path 7 programme (Scientific
Publication Support) requires the SAME grant number in two places in the paper --
the funding statement and the acknowledgements -- and the university's own
figure gives the identifier as:

    26UQU<7-digit staff number>GSSR<2-digit sequence>

An earlier version of this script asserted "six digits then GSSR", which
rejected the real number: the staff field is SEVEN digits, not six. The observed
shape is now the rule.

UQU's own wording attributes the two statements differently, and that difference
is deliberate, not an inconsistency to be flattened:
  funding  : "... funded by Umm Al-Qura University, Saudi Arabia under grant
              number: ..."                      (the University)
  thanks   : "The authors would like to thank the Deanship of Postgraduate
              Studies and Research at Umm Al-Qura University for funding this
              work under grant number: ..."     (the Deanship)
Both say "grant number" and both must carry the SAME value.

The paper must state the number in both sections. While the manuscript is under
review the identifier is carried unfilled as:

    26UQUXXXXXXXGSSRXX

That is a silent failure mode: the file compiles, the PDF renders, the statements
read correctly, and the number is invalid. Nothing else in the pipeline would
notice, so this script does.

The wording is "grant number".

TWO MODES, because "pending" and "broken" are not the same thing.

  Default (review period). The placeholder is REPORTED but not fatal: a manuscript
  under review legitimately has no grant number yet, and a permanently red CI
  would train everyone to ignore it. Malformed or mismatched numbers still fail,
  because those are always wrong.

  --strict (release gate). The placeholder is fatal. Use this before publishing,
  before submitting a revision that claims the award, or in a release workflow.
  A published paper carrying 26UQUXXXXXXXGSSRXX states a grant number that does
  not exist.

It checks both carriers, because they are edited separately and can drift:
  * main.tex, macro \\uquGrant           (funding statement and acknowledgements)
  * the generated cover page, ../peerj-cover.tex (if it carries the number)

Usage:
    python3 check_grant_number.py            # report; fail only on real faults
    python3 check_grant_number.py --strict   # fail on the placeholder too
    python3 check_grant_number.py --quiet

Exit status: 0 if acceptable for the mode, 1 otherwise.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent

# The unfilled form: the 7-digit staff number and 2-digit sequence are not yet issued.
PLACEHOLDER = "26UQUXXXXXXXGSSRXX"

# UQU Path 7 template, observed from the university's own figure:
#   26UQU<7-digit staff number>GSSR<2-digit sequence>
VALID = re.compile(r"^26UQU[0-9]{7}GSSR[0-9]{2}$")

# Correct shape but with unfilled characters, so we can tell "pending" from "typo".
SHAPE = re.compile(r"^26UQU[X0-9]{7}GSSR[X0-9]{2}$")


def from_main_tex() -> str | None:
    text = (HERE / "main.tex").read_text()
    m = re.search(r"\\newcommand\{\\uquGrant\}\{([^}]*)\}", text)
    return m.group(1).strip() if m else None


def from_cover_letter() -> str | None:
    """The grant number in the generated PeerJ cover page, if it carries one."""
    path = HERE.parent / "peerj-cover.tex"
    if not path.exists():
        return None
    m = re.search(r"(26UQU[0-9X]{7}GSSR[0-9X]{2})", path.read_text())
    return m.group(1) if m else None


def is_pending(value: str) -> bool:
    """A correctly shaped identifier that still has unfilled digits."""
    return "X" in value and bool(SHAPE.match(value))


def faults(tex: str | None, cov: str | None) -> list[str]:
    """Problems that are wrong in ANY mode."""
    out: list[str] = []
    if tex is None:
        out.append("main.tex: \\uquGrant is not defined")

    for label, value in (("main.tex", tex), ("peerj-cover.tex", cov)):
        if value is None:
            continue
        if not (VALID.match(value) or is_pending(value)):
            out.append(
                "%s: %r is not a UQU grant number. Expected "
                "26UQU<7-digit staff number>GSSR<2 digits>, or %s while pending."
                % (label, value, PLACEHOLDER))

    if tex is not None and cov is not None and tex != cov:
        out.append(
            "the two carriers disagree: main.tex has %r, peerj-cover.tex has "
            "%r. UQU requires the same number in both." % (tex, cov))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--strict", action="store_true",
                    help="treat the pending placeholder as fatal (use before release)")
    ap.add_argument("--quiet", action="store_true", help="exit code only")
    a = ap.parse_args(argv)

    tex, cov = from_main_tex(), from_cover_letter()
    problems = faults(tex, cov)
    pending = [v for v in (tex, cov) if v and is_pending(v)]

    if not a.quiet:
        print("UQU grant number%s" % ("  [strict]" if a.strict else ""))
        print("  main.tex (\\uquGrant) : %s" % tex)
        print("  peerj-cover.tex       : %s" % cov)
        print()

    if problems:
        if not a.quiet:
            print("BLOCKING:")
            for p in problems:
                print("  - %s" % p)
        return 1

    if pending and a.strict:
        if not a.quiet:
            print("BLOCKING: the grant number is still pending.")
            print("  Both variable fields are issued only on award, so this is")
            print("  expected while the manuscript is under review. It must NOT be")
            print("  published like this: a published paper would state a grant")
            print("  number that does not exist. Fill both carriers from the award")
            print("  letter, then re-run.")
        return 1

    if pending:
        if not a.quiet:
            print("PENDING (not a failure): the number is %r." % PLACEHOLDER)
            print("  Both variable fields are issued on award, so this is correct")
            print("  during review. Run with --strict before publishing.")
        return 0

    if not a.quiet:
        print("OK: both carriers hold the same, complete grant number.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
