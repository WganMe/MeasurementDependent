#!/usr/bin/env python3
"""Decide whether a regenerated result file still agrees with the committed one.

The drift check in `.github/workflows/verify.yml` compares committed results
against a fresh build by asking `git status` whether anything moved. That test
is byte-exact, which is the right default, but it cannot tell two very
different situations apart:

  * a VALUE CHANGED -- the analysis now produces a different number, which is
    exactly the drift the check exists to catch; and
  * the same value came out of a DIFFERENT FLOATING-POINT BUILD -- a different
    numpy/scipy/BLAS rounds the last bits of a dot product or a bootstrap
    differently.

Only the first is a defect. This script separates them, and reports every
difference it finds rather than silently tolerating it.

WHY A TOLERANCE IS NEEDED AT ALL. These analyses are not bit-reproducible
across Python/library versions, and cannot cheaply be made so: they take
eigenvalues of covariance matrices, bootstrap empirical CDFs, and run OLS
through LAPACK. Each of those is a place where a different BLAS or a different
vectorised loop order changes the last one or two bits. Measured on this
project, moving from the maintainer's AlmaLinux/numpy build to the GitHub
Actions ubuntu-24.04 wheels moved 27 numbers, the largest by 3.7e-07 relative
and 26 of them by less than 1e-9. None moved by anything the manuscript's
two-decimal tables could see.

The defaults are therefore set two decades above the worst observed drift:
rtol=1e-5 rejects any change a reader of the paper could detect, while
absorbing last-bit library noise. This is a deliberate, stated trade: it is a
weaker test than byte equality, and the script prints every tolerated
difference so a human can see the noise rather than have it hidden.

WHAT IS NEVER TOLERATED: structure. A missing key, an extra key, a list whose
length changed, a string that changed, a boolean that flipped -- those are
always failures, at any magnitude, because no floating-point build can change
them.

Usage:
    python3 ci_report_drift.py FILE...                       # default tolerance
    python3 ci_report_drift.py --rtol 1e-5 --atol 1e-12 FILE...

Exit status: 0 if every file agrees within tolerance, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import subprocess
import sys

# Two decades above the worst cross-build drift measured on this project
# (3.7e-07 relative, on a bootstrap-resampling estimate).
DEFAULT_RTOL = 1e-5
DEFAULT_ATOL = 1e-12

# How many individual differences to list before summarising the rest.
MAX_LISTED = 60


class Diff:
    """Collects the ways two JSON trees disagree."""

    def __init__(self) -> None:
        self.within: list[tuple[str, float, float]] = []    # tolerated float drift
        self.beyond: list[tuple[str, float, float]] = []    # real numeric change
        self.structure: list[str] = []                      # shape/type mismatch
        self.value: list[tuple[str, object, object]] = []   # non-numeric change

    @property
    def ok(self) -> bool:
        return not (self.beyond or self.structure or self.value)


def is_number(x: object) -> bool:
    # bool is an int subclass; a flipped flag is a real change, not rounding.
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def numbers_agree(a: float, b: float, rtol: float, atol: float) -> bool:
    if a == b:
        return True
    if math.isnan(a) or math.isnan(b) or math.isinf(a) or math.isinf(b):
        return False
    return abs(a - b) <= atol + rtol * abs(b)


def compare(a: object, b: object, rtol: float, atol: float,
            r: Diff, path: str = "") -> None:
    if is_number(a) and is_number(b):
        if not numbers_agree(float(a), float(b), rtol, atol):
            r.beyond.append((path, a, b))
        elif a != b:
            r.within.append((path, a, b))
    elif isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            sub = "%s/%s" % (path, k)
            if k not in a:
                r.structure.append("%s: key added" % sub)
            elif k not in b:
                r.structure.append("%s: key removed" % sub)
            else:
                compare(a[k], b[k], rtol, atol, r, sub)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            r.structure.append("%s: length %d -> %d" % (path, len(a), len(b)))
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                compare(x, y, rtol, atol, r, "%s[%d]" % (path, i))
    elif type(a) is not type(b):
        r.structure.append("%s: type %s -> %s"
                           % (path, type(a).__name__, type(b).__name__))
    elif a != b:
        r.value.append((path, a, b))


def head_text(path: str):
    r = subprocess.run(["git", "show", "HEAD:" + path],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def check(path: str, rtol: float, atol: float) -> bool:
    print("===== %s" % path)
    p = pathlib.Path(path)
    if not p.is_file():
        print("    missing on disk")
        return False

    if not path.endswith(".json"):
        # A changed .tex, .py or .csv is never floating-point noise. Do not
        # accept a tolerance here; say so and fail.
        print("    NOT JSON -- no tolerance applies to this file type.")
        print("    A non-JSON committed file was regenerated differently.")
        return False

    raw = head_text(path)
    if raw is None:
        print("    not in HEAD; treating as an unexplained addition")
        return False

    try:
        old, new = json.loads(raw), json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        print("    not parseable as JSON: %s" % exc)
        return False

    if old == new:
        print("    byte-identical")
        return True

    r = Diff()
    compare(old, new, rtol, atol, r)

    if r.within:
        print("    %d numeric leaf/leaves differ within tolerance "
              "(rtol=%g atol=%g):" % (len(r.within), rtol, atol))
        for pth, a, b in r.within[:MAX_LISTED]:
            rel = abs(b - a) / max(abs(a), 1e-300)
            print("      %-46s %.6g -> %.6g   (rel %.1e)" % (pth, a, b, rel))
        if len(r.within) > MAX_LISTED:
            print("      ... and %d more" % (len(r.within) - MAX_LISTED))
        worst = max(abs(b - a) / max(abs(a), 1e-300) for _, a, b in r.within)
        print("    worst tolerated relative difference: %.2e" % worst)

    for msg in r.structure:
        print("    STRUCTURAL CHANGE: %s" % msg)
    for pth, a, b in r.value:
        print("    VALUE CHANGE: %s: %r -> %r" % (pth, a, b))
    for pth, a, b in r.beyond:
        rel = abs(b - a) / max(abs(a), 1e-300)
        print("    BEYOND TOLERANCE: %s: %.6g -> %.6g   (rel %.1e)"
              % (pth, a, b, rel))

    if r.ok:
        print("    OK: agrees within tolerance"
              + (" (%d float leaves moved)" % len(r.within) if r.within else ""))
    else:
        print("    FAIL: the regenerated file does not match")
    print()
    return r.ok


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="*", help="files that changed during the build")
    ap.add_argument("--rtol", type=float, default=DEFAULT_RTOL,
                    help="relative tolerance for numeric leaves "
                         "(default %(default)s)")
    ap.add_argument("--atol", type=float, default=DEFAULT_ATOL,
                    help="absolute tolerance for numeric leaves "
                         "(default %(default)s)")
    a = ap.parse_args(argv)

    if not a.files:
        print("no files to check")
        return 0

    all_ok = all(check(f, a.rtol, a.atol) for f in a.files)
    if not all_ok:
        print("One or more regenerated files disagree with the committed copy.")
        print("If the difference is a real numeric change, the analysis moved:")
        print("commit the regenerated file, and check whether the manuscript's")
        print("macros still match (verify_paper_numbers.py).")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
