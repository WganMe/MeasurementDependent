#!/usr/bin/env python3
"""Control test for the surname normaliser in verify_references_independent.py.

A checker that reports false failures trains its reader to ignore it, so each
fix to this normaliser must be shown to (a) accept the spellings that are the
same name and (b) still reject spellings that are different names.

Run: python3 control_surname_check.py
Exit: 0 if every expectation holds, 1 otherwise.
"""

import importlib.util
import sys

spec = importlib.util.spec_from_file_location(
    "v", "verify_references_independent.py")
m = importlib.util.module_from_spec(spec)
sys.modules["v"] = m
spec.loader.exec_module(m)

fails = 0


def expect(label, got, want):
    global fails
    ok = got == want
    print(("  OK  " if ok else "  BAD ") + f"{label}: {got!r}"
          + ("" if ok else f"  expected {want!r}"))
    if not ok:
        fails += 1


print("--- same surname written five ways must normalise identically ---")
# NOTE: "Pe\\'aez" is deliberately NOT in this list. It spells "Pe" + accented
# "a" + "ez" -- the name Peaez, not Paez. An earlier version of this test
# asserted it should equal "paez" and the normaliser was right to disagree.
for s in ["P{\\'a}ez", "P{\\'{a}}ez", "p\\'aez", "páez", "paez"]:
    expect(repr(s), m._bib_surname(s), "paez")

print("--- punctuation in a surname must not split one name into two ---")
expect("O'Brien", m._bib_surname("O'Brien"), "obrien")
expect("Al-Nahari", m._bib_surname("Al-Nahari"), "alnahari")

print("--- DataCite creators: the SURNAME, never the given name ---")
expect("name='James, Philip'", m._surname("James, Philip", None, None), "james")
expect("familyName wins", m._surname("James, Philip", "Philip", "James"), "james")
expect("organisation name", m._surname("Newcastle University", None, None),
       "university")

print("--- different names must STILL differ (the check must still bite) ---")
expect("Arbaaeen != Alnahari",
       m._bib_surname("Arbaaeen") == m._bib_surname("Alnahari"), False)
expect("Jonczyk != James",
       m._bib_surname("Jonczyk") == m._bib_surname("James"), False)

print()
if fails:
    print(f"FAILED: {fails} expectation(s) did not hold")
    sys.exit(1)
print("all expectations hold")
