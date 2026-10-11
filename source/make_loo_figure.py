#!/usr/bin/env python3
"""Figure 4 - leave-one-theme-out, on the FIXED full-record hull.

Computed on DEDUPLICATED LOCATIONS, the paper's headline unit, so the figure and
the headline R = 0.202 refer to the same population. Computing this on identifiers
would mix units after the paper has declared locations primary, and would report a
different full-network R (0.155) for a different population.

Removing a theme removes very different numbers of locations (0 to 403), so the
resulting R values are not comparable without their N; the figure therefore shows
the retained location count beside each R, and the dashed line is the full 2026
network.

Usage: python3 make_loo_figure.py
"""
import json
import pathlib
import sys

import numpy as np
from scipy.spatial import ConvexHull
from collections import Counter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analysis_common import load_years, ce_r  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent


def locs_pts(d):
    """Deduplicated locations, matching the paper's headline unit."""
    P = np.array([(v[0], v[1]) for v in d.values()], float)
    return np.unique(np.round(P, 1), axis=0)


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    allP = np.vstack([np.array([(v[0], v[1]) for v in yrs[y].values()], float) for y in years])
    A_hull = float(ConvexHull(allP).volume)

    Y = yrs[2026]
    P = locs_pts(Y)
    themes = Counter(v[2].split("/")[0] for v in Y.values())
    full_r = ce_r(P, A_hull)
    rows = []
    for t in themes:
        # drop every IDENTIFIER of this theme, then deduplicate the survivors, so the
        # location count is the number of distinct places still reporting.
        sel = [(v[0], v[1]) for v in Y.values() if v[2].split("/")[0] != t]
        Q = np.unique(np.round(np.array(sel, float), 1), axis=0)
        rows.append((t, ce_r(Q, A_hull), len(Q)))
    rows.sort(key=lambda r: r[1])

    plt.rcParams.update({"font.size": 8.5, "pdf.fonttype": 42, "axes.grid": True, "grid.alpha": 0.3,
                         "figure.dpi": 300, "savefig.bbox": "tight",
                         "axes.axisbelow": True, "axes.unicode_minus": False})
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    labels = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    ns = [r[2] for r in rows]
    y = np.arange(len(rows))
    ax.barh(y, vals, color="#4c72b0", alpha=0.85, zorder=3)
    for i, (v, m) in enumerate(zip(vals, ns)):
        ax.text(v + 0.004, i, "N=%d" % m, va="center", fontsize=7, color="0.25")
    ax.axvline(full_r, color="#c44e52", ls="--", lw=1.4,
               label="full 2026 locations (N=%d, R=%.3f)" % (len(P), full_r))
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Clark--Evans $R$ on the fixed hull (lower = more clustered)")
    ax.set_xlim(0, max(vals) * 1.35)
    ax.set_title("Leave-one-theme-out on the fixed hull: clustering persists under\n"
                 "every exclusion; the retained location count is shown because it varies 0--403",
                 fontsize=8.6)
    ax.legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "figC6_leave_one_out.pdf")
    print("wrote figures/figC6_leave_one_out.pdf")
    for t, v, m in rows:
        print("  %-15s R=%.3f N=%d" % (t, v, m))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
