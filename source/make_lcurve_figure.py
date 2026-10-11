#!/usr/bin/env python3
"""Figure 3 - the multiscale L curves, on a corrected estimator.

The previous version of this figure used K(r) = A * pairs / (m(m-1)) inside a
CONVEX-HULL window, with no edge correction for the polygon. On a known
complete-spatial-randomness pattern inside the hull that estimator returns a
mean |L| of about 316 m where the answer is exactly 0, drifting to -629 m at
2 km, and the envelope drawn in the old figure was drifting linearly away from
zero for that reason.

This version uses Ripley's border correction on the polygon window
(analysis_multiscale.py), which passes a three-way control: CSR -> L ~ 0,
clustered -> L > 0, regular lattice -> L = -r. Curves are computed on the
DEDUPLICATED LOCATION unit, which is the paper's headline unit.

Usage: python3 make_lcurve_figure.py
"""
import json
import pathlib
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analysis_common import load_years                       # noqa: E402
from analysis_multiscale import (L_border, hull_edges,    # noqa: E402
                                      inward_lines, ids_of, locs_of,
                                      sample_hull, RS)

HERE = pathlib.Path(__file__).resolve().parent


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    allP = np.vstack([ids_of(yrs[y]) for y in years])
    poly, A = hull_edges(allP)
    lines = inward_lines(poly)
    rng = np.random.default_rng(20261003)

    # control: the CSR envelope must sit on zero
    csr = sample_hull(300, poly, rng)
    ctl = L_border(csr, A, lines=lines)
    print("control, CSR n=300, mean |L| = %.1f m (should be ~0)"
          % np.nanmean(np.abs(ctl)))
    print("  " + " ".join("%+7.1f" % v for v in ctl))

    curves = {y: L_border(locs_of(yrs[y]), A, lines=lines) for y in years}
    env = np.array([L_border(sample_hull(200, poly, rng), A, lines=lines)
                    for _ in range(99)])

    plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42, "axes.grid": True, "grid.alpha": 0.3,
                         "figure.dpi": 300, "savefig.bbox": "tight",
                         "axes.axisbelow": True, "axes.unicode_minus": False})
    fig, ax = plt.subplots(figsize=(5.6, 3.3))
    for y in years:
        ax.plot(RS, curves[y], color="0.80", lw=0.7, zorder=1)
    for y, col in ((2013, "#c44e52"), (2020, "#dd8452"), (2026, "#4c72b0")):
        ax.plot(RS, curves[y], color=col, lw=2.0, zorder=3, label=str(y))
    ax.fill_between(RS, np.nanpercentile(env, 2.5, axis=0),
                    np.nanpercentile(env, 97.5, axis=0),
                    color="0.45", alpha=0.22, zorder=0,
                    label="CSR envelope (border-corrected)")
    ax.axhline(0.0, color="k", lw=0.9)
    ax.annotate("randomness, $L=0$", xy=(1180, 250), fontsize=6.8, color="0.25")
    ax.set_xlabel("distance $r$ (m)")
    ax.set_ylabel("$L(r) = \\sqrt{K(r)/\\pi} - r$  (m)")
    ax.set_xlim(0, 2000)
    ax.set_title("Ripley $L$ on the fixed full-record hull, deduplicated locations\n"
                 "positive at every scale in every year; envelope sits on zero",
                 fontsize=8.6)
    ax.legend(fontsize=7, loc="upper left")
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "figC7_lcurve.pdf")
    print("wrote figures/figC7_lcurve.pdf")

    norm = {y: curves[y] / curves[y][-1] for y in years if curves[y][-1] != 0}
    i5 = int(np.where(RS == 500)[0][0]); i10 = int(np.where(RS == 1000)[0][0])
    print("normalised excess at 500 m : 2020 %.3f -> 2026 %.3f"
          % (norm[2020][i5], norm[2026][i5]))
    print("normalised excess at 1000 m: 2020 %.3f -> 2026 %.3f"
          % (norm[2020][i10], norm[2026][i10]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
