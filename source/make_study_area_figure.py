#!/usr/bin/env python3
"""Figure C0: the study area, and where the instruments actually are.

A spatial paper with no picture of its study area is hard to review, and this one
has been asking readers to hold a 4416 km2 convex hull, a 2013 network occupying a
quarter of it, and a 17x growth in their heads. This figure shows the hull, the
per-year extent, and the 2013 against the 2026 locations on the same axes.

Matplotlib only, no basemap: the point is the geometry of the frame, not coastlines.

Writes: figures/figC0_study_area.pdf
"""
from __future__ import annotations

import json
import pathlib
import sys

import matplotlib

# Type 3 bitmap fonts are rejected by journal production and break pdftex
# microtype; embed TrueType outlines instead (matplotlib default is 3).
matplotlib.rcParams["pdf.fonttype"] = 42
# SET THE TICK-LABEL MINUS FROM THE FONT'S ASCII HYPHEN-MINUS. Matplotlib otherwise
# labels negative ticks with U+2212 MINUS SIGN. The subset of DejaVuSans that gets
# embedded for the axes carries no ToUnicode entry for that glyph (verified: the
# embedded subsets list no 0x2212 target), so anything that re-encodes the PDF -- as
# PeerJ's production pipeline does -- drops the sign and a reader, a search engine or
# a screen reader sees "2200" where the axis reads "-200". The ASCII hyphen survives
# every encoding. Visual difference is a slightly shorter minus; the axis stays correct.
matplotlib.rcParams["axes.unicode_minus"] = False
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon as MplPoly

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analysis_common import load_years  # noqa: E402
from analysis_multiscale import locs_of, hull_edges  # noqa: E402


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    allP = np.vstack([locs_of(yrs[y]) for y in years])
    poly, A = hull_edges(allP)

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.6))

    # ---- panel (a): the hull and both endpoint networks ---------------------
    ax = axes[0]
    ax.add_patch(MplPoly(poly / 1000.0, closed=True, facecolor="#f2f2f2",
                         edgecolor="#888888", lw=1.0, zorder=1,
                         label="fixed reference hull (%.0f km$^2$)" % (A / 1e6)))
    P13 = locs_of(yrs[2013]) / 1000.0
    P26 = locs_of(yrs[2026]) / 1000.0
    ax.scatter(P26[:, 0], P26[:, 1], s=9, c="#1f77b4", alpha=0.55, lw=0,
               label="2026 locations (%d)" % len(P26), zorder=2)
    ax.scatter(P13[:, 0], P13[:, 1], s=46, c="#d62728", marker="^", alpha=0.95,
               edgecolor="white", lw=0.6, label="2013 locations (%d)" % len(P13),
               zorder=3)
    ax.set_aspect("equal")
    ax.set_xlabel("east of projection origin (km)")
    ax.set_ylabel("north of projection origin (km)")
    ax.set_title("(a) the frame, and the two endpoint networks")
    ax.legend(loc="upper left", fontsize=7, framealpha=0.9)

    # ---- panel (b): how much of the hull each year fills -------------------
    ax = axes[1]
    frac = []
    for y in years:
        P = locs_of(yrs[y]) / 1000.0
        lo, hi = P.min(axis=0), P.max(axis=0)
        frac.append(100.0 * (hi[0] - lo[0]) * (hi[1] - lo[1]) / (A / 1e6))
    ax.plot(years, frac, "o-", color="#2ca02c", lw=1.4, ms=4)
    ax.axhline(100.0, color="#888888", ls="--", lw=1.0)
    ax.text(years[0], 103, "the hull itself", fontsize=7, color="#666666")
    ax.set_xlabel("year")
    ax.set_ylabel("per-year bounding box, % of hull area")
    ax.set_title("(b) the network fills a growing share of the frame")
    ax.set_ylim(0, 112)
    ax.grid(alpha=0.25, lw=0.5)
    for y, f in ((2013, frac[0]), (2021, frac[years.index(2021)])):
        ax.annotate("%.0f%%" % f, (y, f), textcoords="offset points",
                    xytext=(0, 7), fontsize=7, ha="center")

    fig.suptitle("Study area: Newcastle Urban Observatory, 2013-2026", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = HERE / "figures" / "figC0_study_area.pdf"
    fig.savefig(out, bbox_inches="tight")
    print("wrote %s" % out)
    print("  hull %.0f km2; 2013 box %.1f%% of it; 2026 box %.1f%%"
          % (A / 1e6, frac[0], frac[-1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
