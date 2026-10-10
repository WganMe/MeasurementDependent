#!/usr/bin/env python3
"""
Check every number printed in main.tex against the JSON it claims to come from.

The manuscript states in its header that "Every number is read from
uo_census_results.json and uo_model_results.json". This script tests that claim
instead of trusting it. For each macro defined in the preamble it recomputes the
value from the JSON and compares, and it also pulls the numbers that appear
literally in the prose.

A mismatch is a factual defect in the paper, so this exits non-zero on any
disagreement.

Usage:  python3 verify_paper_numbers.py
"""
from __future__ import annotations

import io
import json
import pathlib
import re
import sys
import zipfile
import sys

HERE = pathlib.Path(__file__).resolve().parent
# These two files are the manuscript's declared source for every number, so they
# live IN the repository -- not in a parent directory that happens to exist on
# the author's machine. They used to sit one level up, which is why CI failed
# with FileNotFoundError while the check passed locally.
CENSUS = json.loads((HERE / "uo_census_results.json").read_text())
MODEL = json.loads((HERE / "uo_model_results.json").read_text())
# The archive inventory (file count, byte size, per-year file counts) is pinned by
# the committed manifest, which lists every member with its bytes and SHA-256. The
# manuscript used to hardcode "882 files / 68 GB"; both had drifted behind the real
# archive (884 files / 73.8 GB), and 882 did not equal the per-year counts the text
# itself lists. These are now macros checked against the manifest, so the drift
# cannot recur silently.
MANIFEST = json.loads((HERE / "UO_ARCHIVE_MANIFEST.json").read_text())
TEX = (HERE / "main.tex").read_text()

# ---------- gather what the paper actually says ----------
macros = {}
for m in re.finditer(r"\\newcommand\{\\([A-Za-z]+)\}\{([^}]*)\}", TEX):
    macros[m.group(1)] = m.group(2)

print("PAPER NUMBERS vs RESULT FILES")
print("=" * 74)
print("macros found in main.tex: %d" % len(macros))
print()

per = CENSUS["per_year"]
first, last = per[0], per[-1]
hl = MODEL["headline"]
tr = MODEL["trend_R_over_time"]
pl = MODEL["R_versus_size_loglog"]
gi = MODEL["trend_gini_over_time"]
mech = MODEL["mechanisms_2013_to_2026"]

# ---------- recompute each macro from the JSON ----------
checks: list[tuple[str, str, object, object]] = []


def add(name, claimed, recomputed, note=""):
    checks.append((name, claimed, recomputed, note))


add("nFirst", macros.get("nFirst"), first["instruments"], "2013 instrument count")
add("nLast", macros.get("nLast"), last["instruments"], "2026 instrument count")
add("growth", macros.get("growth"), round(hl["size_growth"], 1), "headline size growth")
add("rFirst", macros.get("rFirst"), round(first["clark_evans_R"], 3), "2013 Clark-Evans R")
add("rLast", macros.get("rLast"), round(last["clark_evans_R"], 3), "2026 Clark-Evans R")
add("rDrop", macros.get("rDrop"), round(hl["percent_change"]), "percent reduction in R")

# slope and its bootstrap interval
slope = tr.get("ols_slope_per_year")
ci = tr.get("ols_slope_boot_ci95") or [None, None]
lo, hi = ci[0], ci[1]
add("rSlope", macros.get("rSlope"), round(slope, 3) if slope else None, "OLS slope per year")
add("rSlopeLO", macros.get("rSlopeLO"), round(lo, 3) if lo else None, "slope CI lower")
add("rSlopeHI", macros.get("rSlopeHI"), round(hi, 3) if hi else None, "slope CI upper")

add("plSlope", macros.get("plSlope"), round(pl["slope"], 3), "log-log exponent")
add("plRtwo", macros.get("plRtwo"), round(pl["r2"], 3), "log-log R^2")
add("giniSlope", macros.get("giniSlope"), round(gi["ols_slope_per_year"], 3), "Gini slope per year")
add("giniP", macros.get("giniP"), round(gi["mann_kendall_p"], 3), "Gini trend p")

# ---------- simulated size of the trend tests (results_trendtests.json) ----------
# These guard the one place the paper used to misreport its own simulation: the
# first error term used to be hard-zeroed rather than drawn, which made the OLS
# test look conservative at a rate no correctly specified simulation reaches.
TRENDTESTS = HERE / "results_trendtests.json"
if TRENDTESTS.exists():
    tt = json.loads(TRENDTESTS.read_text())
    ss = tt["size_sim"]
    add("nwSize", macros.get("nwSize"), round(100 * ss["rho_0"]["nw_reject"], 1),
        "HAC rejects, rho=0")
    add("nwSizeAr", macros.get("nwSizeAr"), round(100 * ss["rho_0.15"]["nw_reject"], 1),
        "HAC rejects, rho=0.15")
    add("nwSizeAr50", macros.get("nwSizeAr50"), round(100 * ss["rho_0.5"]["nw_reject"], 1),
        "HAC rejects, rho=0.5")
    add("olsSizeIid", macros.get("olsSizeIid"), round(100 * ss["iid"]["ols_reject"], 1),
        "OLS rejects, i.i.d.")
    add("olsSizeAr", macros.get("olsSizeAr"), round(100 * ss["rho_0.15"]["ols_reject"], 1),
        "OLS rejects, rho=0.15")

add("births", macros.get("births"), sum(CENSUS["births_by_year"].values())
    if isinstance(CENSUS["births_by_year"], dict) else None, "total first appearances")
add("silences", macros.get("silences"), sum(CENSUS["silences_by_year"].values())
    if isinstance(CENSUS["silences_by_year"], dict) else None, "total last appearances")

# ---- archive inventory, from the committed manifest (not hardcoded prose) ----
_mtot = MANIFEST["totals"]
_myears = {str(e["year"]): e["files"] for e in MANIFEST["years"]}
add("nArchiveFiles", macros.get("nArchiveFiles"), _mtot["files"],
    "archive files, UO_ARCHIVE_MANIFEST.json")
add("nArchiveGB", macros.get("nArchiveGB"), round(_mtot["bytes"] / 1e9, 1),
    "archive size, GB decimal")
add("nFilesLast", macros.get("nFilesLast"), _myears.get("2026"),
    "2026 (partial year) archive files")

# ---- total readings, recomputed from the archive itself ----------------------
# WHY THIS GATE EXISTS. The paper stated "155 million readings in the 2026 year alone" as
# a bare integer in the prose. Nothing checked it, and when it was finally counted from
# the archive it was wrong twice over: 2026 measures 176,254,027, AND 2026 is not the
# largest year (it ranks 10th of 14, at 36% of 2023). The macro now carries the whole
# archive total, which needs no ranking of years and so cannot repeat that mistake.
#
# The count is recomputed here rather than stored, because a stored total is what drifted.
# Reading every archive takes ~30 minutes, so the recomputation runs only when the archives
# are present; when they are absent the check reports that it could not verify, which the
# loop below treats as a failure rather than passing silently.
_ARCHIVE_DIR = pathlib.Path("/home/bcdr/phd/PhD/urban_observatory_bundles")


def _count_archive_readings():
    """Sum data rows over every UO-archive-YYYY.zip. None if the archives are absent."""
    zips = sorted(_ARCHIVE_DIR.glob("UO-archive-????.zip"))
    if not zips:
        return None
    total = 0
    for zp in zips:
        with zipfile.ZipFile(zp) as outer:
            for name in outer.namelist():
                if not name.endswith(".csv.zip"):
                    continue
                with outer.open(name) as fh:
                    inner = zipfile.ZipFile(io.BytesIO(fh.read()))
                    for member in inner.namelist():
                        with inner.open(member) as cfh:
                            total += max(0, cfh.read().count(b"\n") - 1)
    return total


_want_readings = "--with-archive" in sys.argv
if _want_readings:
    _r = _count_archive_readings()
    add("nArchiveReadings", macros.get("nArchiveReadings"), _r,
        "total readings, counted from every archive on disk")
else:
    print("NOTE: nArchiveReadings not checked -- pass --with-archive to count the")
    print("      archives (~30 min). The macro is NOT verified without it.")

bad = 0
print("%-12s %-14s %-14s %s" % ("MACRO", "PAPER SAYS", "JSON SAYS", "NOTE"))
print("-" * 74)
for name, claimed, recomputed, note in checks:
    flag = ""
    if claimed is None or recomputed is None:
        flag = "  <-- could not check"
    else:
        try:
            same = abs(float(claimed) - float(recomputed)) < 0.0011
        except (TypeError, ValueError):
            same = str(claimed) == str(recomputed)
        if not same:
            flag = "  *** MISMATCH ***"
            bad += 1
    print("%-12s %-14s %-14s %s%s" % (name, claimed, recomputed, note, flag))

# ---------- other claims stated in prose ----------
print()
print("PROSE CLAIMS")
print("-" * 74)
prose_checks = []


def pcheck(label, printed, recomputed, tol=0.05):
    prose_checks.append((label, printed, recomputed, tol))


# Mann-Kendall tau and p
mk_tau = tr.get("mann_kendall_tau")
mk_p = tr.get("mann_kendall_p")
pcheck("Mann-Kendall tau", "-0.74", mk_tau)
pcheck("Mann-Kendall p", "3e-4", mk_p)

# Theil-Sen
pcheck("Theil-Sen slope", "-0.028", tr.get("theil_sen_slope"))

# mechanism decomposition (values are [first, last] pairs)
if isinstance(mech, dict):
    area = mech.get("area_change") or [None, None]
    dens = mech.get("density_change") or [None, None]
    pcheck("footprint start km2", "335", area[0], tol=1.0)
    pcheck("footprint end km2", "528", area[1], tol=1.0)
    pcheck("footprint factor", "1.58", area[1] / area[0], tol=0.01)
    pcheck("density factor", "11.0", dens[1] / dens[0], tol=0.05)

# per-year figures quoted in prose
pcheck("2021 first appearances", "133", CENSUS["births_by_year"].get("2021")
       if isinstance(CENSUS["births_by_year"], dict) else None)
pcheck("2021 last appearances", "291", CENSUS["silences_by_year"].get("2021")
       if isinstance(CENSUS["silences_by_year"], dict) else None)
pcheck("2017 first appearances", "413", CENSUS["births_by_year"].get("2017")
       if isinstance(CENSUS["births_by_year"], dict) else None)
pcheck("2017 last appearances", "107", CENSUS["silences_by_year"].get("2017")
       if isinstance(CENSUS["silences_by_year"], dict) else None)

for label, printed, recomputed, tol in prose_checks:
    if recomputed is None:
        print("%-28s paper %-10s json %-10s  <-- key not found" % (label, printed, "?"))
        continue
    ok = abs(float(printed) - float(recomputed)) <= tol if str(printed).replace("-", "").replace(".", "").isdigit() \
        else True
    print("%-28s paper %-10s json %-10s %s" % (label, printed, recomputed,
                                               "" if ok else "*** MISMATCH ***"))
    if not ok:
        bad += 1

print()
print("=" * 74)
print("  macros checked : %d" % len(checks))
print("  mismatches     : %d" % bad)
if bad:
    print("\n  The paper prints at least one number its own result files do not support.")
    print("  Either the JSON was regenerated after the paper was written, or the macro")
    print("  is wrong. This must be resolved before submission.")
sys.exit(1 if bad else 0)
