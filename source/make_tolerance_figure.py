#!/usr/bin/env python3
"""Figure 8 - what the co-location merge does, and why the tolerance is a choice.

The main text reports that the headline fall in the Clark-Evans index collapses
from 45% to 4.3% when co-located identifiers are merged at a 25 m tolerance.
Two things a reader needs in order to judge that, and which no table gives:

  (a) the whole sweep, not one chosen point. The fall is monotone in the
      tolerance and there is no plateau: it continues past the point of use and
      changes sign, so 25 m is not "where the artefacts stop", it is one rung on
      a continuum. The 5% significance line moves with it.

  (b) the nearest-neighbour distribution, which is where a justification for the
      tolerance would have to live. If co-located registrations formed a
      distinct population separated from distinct installations by a trough, a
      threshold in that trough would be defensible. There is no trough.

Left panel: fall and p-value against tolerance, on a log x axis.
Right panel: the pooled nearest-neighbour distance distribution, in 1 m bins,
for the recent full years, on a log x axis.

Usage: python3 make_tolerance_figure.py
"""
import json
import pathlib
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter, NullFormatter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analysis_common import load_years                       # noqa: E402
from analysis_multiscale import ids_of                        # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent


def main() -> int:
    res = json.loads((HERE / "results_tolerance.json").read_text())
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)

    sweep = res["sweep"]
    tol = np.array([s["tol_m"] for s in sweep])
    fall = np.array([s["fall_pct"] for s in sweep])
    pval = np.array([s["p"] for s in sweep])

    plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42, "axes.grid": True, "grid.alpha": 0.3,
                         "figure.dpi": 300, "savefig.bbox": "tight",
                         "axes.axisbelow": True, "axes.unicode_minus": False})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.4, 3.1))

    # ---------------------------------------------------------------- panel A
    ax1.plot(tol, fall, "o-", color="#4c72b0", lw=1.8, ms=4.5,
             label="fall in $R$, 2013$\\rightarrow$2026")
    ax1.axhline(0, color="k", lw=0.9)
    ax1.axvline(25, color="#c44e52", lw=1.2, ls="--")
    ax1.annotate("25 m, used in the text", xy=(25, 34), fontsize=6.6,
                 color="#c44e52", rotation=90, va="top")
    ax1.set_xscale("log")
    ax1.set_xlabel("merge tolerance (m)")
    ax1.set_ylabel("fall in $R$ (%)")
    ax1.set_ylim(-14, 52)

    ax1b = ax1.twinx()
    ax1b.plot(tol, pval, "s--", color="#55a868", lw=1.3, ms=3.5, alpha=0.9)
    ax1b.axhline(0.05, color="#55a868", lw=0.8, ls=":", alpha=0.7)
    ax1b.set_ylabel("$p$ (dashed, right)", color="#55a868")
    ax1b.tick_params(axis="y", colors="#55a868")
    ax1b.set_yscale("log")
    ax1b.set_ylim(0.02, 1.2)
    # A log axis labels its decades with mathtext ("10^{-1}"), and mathtext sets its
    # minus from the math-symbol font regardless of axes.unicode_minus. That glyph has
    # no ToUnicode entry in the embedded subset, so the tick extracts as "101" instead
    # of "10-1" once a production pipeline re-encodes the PDF. Plain decimals avoid
    # mathtext altogether and read better on a p-value axis.
    _fmt = ScalarFormatter()
    _fmt.set_scientific(False)
    ax1b.yaxis.set_major_formatter(_fmt)
    ax1b.yaxis.set_minor_formatter(NullFormatter())
    ax1.grid(False)
    ax1b.grid(False)
    ax1.set_title("(a) the tolerance is a continuum, not a plateau", fontsize=8.4)

    # ---------------------------------------------------------------- panel B
    edges = np.arange(0.5, 300.5, 1.0)
    for y, col in ((2020, "#dd8452"), (2026, "#4c72b0")):
        P = ids_of(yrs[y])
        d = np.sort(np.linalg.norm(
            P[:, None, :] - P[None, :, :], axis=2))[:, 1]  # nearest neighbour
        h, _ = np.histogram(d, bins=edges)
        ax2.step(edges[:-1], h, where="post", color=col, lw=1.6, label=str(y))
    ax2.set_xscale("log")
    ax2.axvline(25, color="#c44e52", lw=1.2, ls="--")
    ax2.set_xlabel("nearest-neighbour distance (m)")
    ax2.set_ylabel("identifiers")
    ax2.legend(fontsize=7)
    ax2.set_title("(b) no trough between co-located and distinct sites",
                  fontsize=8.4)

    fig.tight_layout()
    fig.savefig(HERE / "figures" / "figC8_tolerance.pdf")
    print("wrote figures/figC8_tolerance.pdf")

    i = int(np.argmin(np.abs(tol - 25)))
    print("at 25 m: fall %.1f%%, p = %.3f" % (fall[i], pval[i]))
    print("fall is monotone in tolerance:", bool(np.all(np.diff(fall) < 0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
