#!/usr/bin/env python3
"""Figure 2 - Clark-Evans R by year on the FIXED full-record hull.

Both units are drawn: the location series (the headline) and the identifier series,
each with a HAC (lag 2) trend interval. The rarefied series is shown faintly so a
reader can see the null the text reports. The per-year-box series is not drawn,
because the paper's own lesson is to fix the window; it is in Table 3.

Usage: python3 make_clustering_figure.py
"""
import json
import pathlib
import sys

import numpy as np
from scipy.spatial import ConvexHull
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analysis_common import load_years, ce_r  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent


def ids_pts(d):
    return np.array([(v[0], v[1]) for v in d.values()], float)


def locs_of(d):
    return np.unique(np.round(ids_pts(d), 1), axis=0)


def ols_hac_slope(Y, v, lag=2):
    X = np.column_stack([np.ones(len(Y)), Y])
    XtX = np.linalg.pinv(X.T @ X)
    b = XtX @ X.T @ v
    r = v - X @ b
    n, k = X.shape
    S = np.zeros((k, k))
    for t in range(n):
        S += (r[t] ** 2) * (X[t][:, None] @ X[t][:, None].T)
    for l in range(1, lag + 1):
        w = 1 - l / (lag + 1)
        for t in range(l, n):
            G = r[t] * r[t - l] * (X[t][:, None] @ X[t - l][:, None].T)
            S += w * (G + G.T)
    cov = XtX @ S @ XtX
    return float(b[1]), np.sqrt(np.diag(cov))[1]


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    Y = np.array(years, float)
    allP = np.vstack([ids_pts(yrs[y]) for y in years])
    A_hull = float(ConvexHull(allP).volume)

    ids_ser = np.array([ce_r(ids_pts(yrs[y]), A_hull) for y in years])
    loc_ser = np.array([ce_r(locs_of(yrs[y]), A_hull) for y in years])
    rare = json.loads((HERE / "results_rarefied.json").read_text())
    rare_ser = np.array(rare["R7.2_rarefied_R"]["rarefied"])

    plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42, "axes.grid": True, "grid.alpha": 0.3,
                         "figure.dpi": 300, "savefig.bbox": "tight",
                         "axes.axisbelow": True, "axes.unicode_minus": False})
    fig, ax = plt.subplots(figsize=(5.6, 3.3))
    ax.plot(Y, rare_ser, color="0.7", lw=1.0, ls=":", marker="o", ms=2.6,
            zorder=2, label="rarefied to $N=41$ identifiers")
    ax.plot(Y, ids_ser, color="#c44e52", lw=1.6, marker="o", ms=3.2, zorder=3,
            label="identifiers (hull)")
    ax.plot(Y, loc_ser, color="#4c72b0", lw=2.0, marker="s", ms=3.2, zorder=4,
            label="locations (hull, headline)")
    # HAC trend lines
    for ser, col in ((ids_ser, "#c44e52"), (loc_ser, "#4c72b0")):
        sl, _ = ols_hac_slope(Y, ser)
        ax.plot(Y, ser[0] + sl * (Y - Y[0]), color=col, lw=0.9, ls="--", alpha=0.7,
                zorder=3)
    ax.axhline(1.0, color="k", lw=0.8)
    ax.annotate("randomness", xy=(2013.2, 1.02), fontsize=7, color="0.3")
    ax.set_xlabel("year")
    ax.set_ylabel("Clark--Evans $R$")
    ax.set_ylim(0, 1.15)
    ax.set_title("Clark--Evans $R$ on the fixed full-record hull, both units\n"
                 "rarefying to a common $N$ removes the trend",
                 fontsize=8.6)
    ax.legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "figC2_clustering.pdf")
    print("wrote figures/figC2_clustering.pdf")
    for nm, ser in (("ids", ids_ser), ("locs", loc_ser), ("rarefied", rare_ser)):
        sl, se = ols_hac_slope(Y, ser)
        print("  %-9s slope %+.4f (HAC se %.4f)  %.3f -> %.3f"
              % (nm, sl, se, ser[0], ser[-1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
