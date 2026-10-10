#!/usr/bin/env python3
"""Check the CRediT contribution statement, and derive what the submission form should show.

WHY THIS EXISTS. The submission form asks for each author's Contributor Roles, ticked
from the 14-term CRediT taxonomy. The ticked set has to say the same thing as the
`\\authorcontributions` statement in main.tex: the form is what the editorial office
reads first, the statement is what a referee reads later, and a disagreement between
them is a claim that cannot be defended.

Three specific defects motivated this file, all observed on the real form:

  1. All 14 roles were ticked for the first author. The complete taxonomy is not a
     contribution profile - it is a "select all" - and the submission form asks for a statement that
     specifies each author's individual contributions.

  2. "Supervision" was ticked for the first author. A referee had already required
     that role's removal from this manuscript (admin/review/REFEREE_AUDIT.md, item C8)
     and the statement no longer carries it, so re-ticking it reinstates the exact
     criticism that was already answered.

  3. "Funding acquisition" was absent from the statement entirely, even though the
     paper declares UQU funding. The grant is issued against a UQU employee number,
     and the author holding it is the UQU author - not the KAU or independent one.

The initials in the statement are ambiguous by design: W.A. is Wael Alnahari while
W.Al. is Wasem Alnahri. The mapping to full names is therefore declared here rather
than inferred, and an unrecognised initial is a failure rather than a silent omission.

Usage:
    python3 check_credit_roles.py             # validate main.tex
    python3 check_credit_roles.py --for-form  # print the roles to tick, per author

Exit status: 0 if the statement is sound, 1 otherwise.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
TEX = HERE / "main.tex"

# The 14 CRediT terms the form offers, with its checkbox value for each. The value
# lets a reader go straight to the box to untick instead of scanning for a label.
CREDIT = [
    ("Conceptualization", 1), ("Data curation", 2), ("Formal analysis", 3),
    ("Funding acquisition", 4), ("Investigation", 5), ("Methodology", 6),
    ("Project administration", 7), ("Resources", 8), ("Software", 9),
    ("Supervision", 10), ("Validation", 11), ("Visualization", 12),
    ("Writing \u2013 original draft", 13), ("Writing \u2013 review & editing", 14),
]
TAXONOMY = {name.lower() for name, _ in CREDIT}
# The statement spells the writing roles in prose rather than with an en dash.
ROLE_ALIASES = {
    "writing (original draft preparation)": "writing \u2013 original draft",
    "writing (review and editing)": "writing \u2013 review & editing",
}
# Needles to scan a role phrase for, longest first so the alias wins over a substring
# of itself. Built from TAXONOMY plus the aliases, so a new CRediT term is picked up
# automatically while an alias still takes precedence.
_PATTERNS: list[tuple[str, str]] = sorted(
    [(alias, target) for alias, target in ROLE_ALIASES.items()]
    + [(term, term) for term in TAXONOMY],
    key=lambda kv: -len(kv[0]))

# Initial -> (full name, institution, is UQU). Declared, not inferred: W.A. and W.Al.
# differ by one letter and the statement relies on that difference.
AUTHORS = {
    "W.A.":  ("Wael Alnahari", "KAU", False),
    "T.H.":  ("Tawfiq Hasanin", "KAU", False),
    "A.Ar.": ("Ammar Arbaaeen", "UQU", True),
    "A.Al.": ("Ammar Alsaig", "UQU", True),
    "W.Al.": ("Wasem Alnahri", "Independent", False),
}

# The sentence that closes the statement; not a role assignment.
CLOSING = re.compile(
    r"All authors have read and agreed to the published version of the manuscript\.",
    re.IGNORECASE)
INITIAL = re.compile(r"\b[A-Z]\.[A-Z][a-z]*\.")


def statement() -> str:
    m = re.search(r"\\authorcontributions\{(.*?)\}", TEX.read_text(), re.DOTALL)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def split_roles(role_part: str) -> list[str]:
    """Canonicalise the role side of one ';'-separated segment.

    A segment can carry more than one role: the writing roles are written as
    "writing (original draft preparation) and writing (review and editing), W.A., ...".

    Splitting that on " and " does NOT work, because " and " also occurs inside
    "(review and editing)": the phrase fragments into 'writing (review' and 'editing)',
    and both are then discarded - which silently dropped the review-and-editing role
    for every author. So the roles are FOUND by scanning for known phrases instead of
    being recovered by splitting. Longest needle first, so an alias is preferred over
    any shorter substring of it.
    """
    low = role_part.lower()
    found: list[str] = []
    for needle, target in _PATTERNS:
        if needle in low and target not in found:
            found.append(target)
    return found


def roles_by_author(text: str) -> dict[str, set[str]]:
    """Map each author's initials to the set of roles the statement gives them."""
    out: dict[str, set[str]] = {k: set() for k in AUTHORS}
    for segment in CLOSING.sub("", text).split(";"):
        segment = segment.strip()
        if not segment:
            continue
        role_part, _, rest = segment.partition(",")
        for role in split_roles(role_part):
            for who in INITIAL.findall(rest):
                if who in out:
                    out[who].add(role)
    return out


def check(text: str, roles: dict[str, set[str]]) -> list[str]:
    problems: list[str] = []
    if not text:
        return ["main.tex has no \\authorcontributions statement"]

    # An initial in the statement that is not in AUTHORS would be silently dropped by
    # roles_by_author, under-reporting someone's contribution. Find those directly.
    for who in set(INITIAL.findall(CLOSING.sub("", text))):
        if who not in AUTHORS:
            problems.append(
                "%s appears in the contribution statement but is not in the author map "
                "in this file, so its roles are not being checked" % who)

    every = set(TAXONOMY)
    for who, got in roles.items():
        name = AUTHORS[who][0]
        unknown = got - every
        for r in sorted(unknown):
            problems.append("%s has a role that is not a CRediT term: %r" % (name, r))
        if got == every:
            problems.append(
                "%s is assigned all 14 CRediT roles. That is a select-all, not a "
                "contribution profile." % name)

    # A referee already required Supervision's removal from this manuscript. The form
    # and the statement must not disagree about it.
    if "supervision" in roles.get("W.A.", set()):
        problems.append(
            "W.A. (Wael Alnahari) is assigned Supervision. A referee required this "
            "role's removal and the statement was corrected; restore it only if you "
            "also record the referee round that reverses that decision.")

    # The UQU grant is issued against a UQU employee number, so funding acquisition
    # belongs to a UQU author and to no one else.
    for who, got in roles.items():
        name, inst, is_uqu = AUTHORS[who]
        if "funding acquisition" in got and not is_uqu:
            problems.append(
                "%s (%s) is assigned Funding acquisition, but the declared grant is "
                "issued by UQU. The eligible applicant is the UQU author."
                % (name, inst))

    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--for-form", action="store_true",
                    help="print the roles to tick for each author, then exit")
    ap.add_argument("--quiet", action="store_true", help="exit code only")
    a = ap.parse_args(argv)

    text = statement()
    roles = roles_by_author(text)

    if a.for_form:
        print("Contributor Roles to tick in the submission form")
        print("(derived from the \\authorcontributions statement in main.tex)\n")
        for who, (name, inst, _) in AUTHORS.items():
            got = roles.get(who, set())
            print("%s  --  %s (%s)" % (who, name, inst))
            if not got:
                print("    (no roles recorded in the statement)")
            for role, value in CREDIT:
                if role.lower() in got:
                    print("    tick    %-30s value=%d" % (role, value))
            print()
        return 0

    problems = check(text, roles)
    if not a.quiet:
        print("CRediT contribution statement")
        for who, (name, inst, _) in AUTHORS.items():
            n = len(roles.get(who, set()))
            print("  %-6s %-18s %-12s %d role%s"
                  % (who, name, inst, n, "" if n == 1 else "s"))
        print()
    if problems:
        if not a.quiet:
            print("BLOCKING:")
            for p in problems:
                print("  - %s" % p)
        return 1
    if not a.quiet:
        print("OK: the statement is a valid CRediT assignment and is internally consistent.")
        print("    Compare it against the form with:  python3 check_credit_roles.py --for-form")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
