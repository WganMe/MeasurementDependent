#!/usr/bin/env python3
"""Round 16d: does the Gini depend on where the fixed grid starts?

The concentration index is computed on a grid anchored in geographic space. The
anchor is arbitrary: a cell boundary a few hundred metres either way would
reassign instruments between cells. If the index's *trend* is sensitive to the
anchor, the concentration result is reporting the grid rather than the network.

Sweeps the origin over a 5x5 lattice of sub-cell shifts at the headline
resolution (20 cells per side) and at a finer one (40), and also re-checks
Equation (1) against the textbook form to make sure the paper's formula and the
code agree.

Writes: results_gridorigin.json
"""
from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analysis_common import load_years, ols_hac, gini_fixed_grid  # noqa: E402
from analysis_multiscale import locs_of  # noqa: E402


def gini_eq1(counts: np.ndarray) -> float:
    """Equation (1) of the paper, written exactly as printed."""
    c = np.sort(np.asarray(counts, float))
    n = len(c)
    tot = c.sum()
    i = np.arange(1, n + 1)
    return float((n + 1) / n - (2.0 / (n * tot)) * np.sum((n - i + 1) * c))


def gini_textbook(counts: np.ndarray) -> float:
    """The standard form, for the equivalence check."""
    c = np.sort(np.asarray(counts, float))
    n = len(c)
    tot = c.sum()
    i = np.arange(1, n + 1)
    return float((2.0 * np.sum(i * c) / (n * tot)) - (n + 1.0) / n)


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    idx = json.loads((here / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)

    res: dict = {"years": years}

    # ---- equivalence check: does the printed formula equal the textbook one? --
    rng = np.random.default_rng(20261003)
    worst = 0.0
    for _ in range(2000):
        k = int(rng.integers(3, 60))
        counts = rng.integers(1, 20, size=k)
        worst = max(worst, abs(gini_eq1(counts) - gini_textbook(counts)))
    res["equation1_max_abs_diff"] = float(worst)
    print("[1] Equation (1) vs the textbook form over 2000 random count vectors")
    print("    maximum absolute difference: %.3e" % worst)
    print("    -> %s" % ("identical to machine precision"
                         if worst < 1e-12 else "MISMATCH, investigate"))
    print()

    # ---- origin sensitivity ------------------------------------------------
    for nx in (20, 40):
        P_all = np.asarray([q for y in years for q in locs_of(yrs[y])], float)
        x0, y0 = P_all[:, 0].min(), P_all[:, 1].min()
        x1, y1 = P_all[:, 0].max(), P_all[:, 1].max()
        cell = max(x1 - x0, y1 - y0) / nx
        base = (x0 - 0.02 * cell, y0 - 0.02 * cell)

        slopes, firsts, lasts = [], [], []
        for fx in np.linspace(0.0, 1.0, 5):
            for fy in np.linspace(0.0, 1.0, 5):
                org = (base[0] + fx * cell, base[1] + fy * cell)
                G = np.array([gini_fixed_grid(
                    np.asarray(locs_of(yrs[y]), float), org, cell, nx)
                    for y in years], float)
                if np.isnan(G).any():
                    continue
                Yr = np.array(years, float)
                X = np.column_stack([np.ones_like(Yr), Yr])
                beta, se, r2, _ = ols_hac(G, X, 2)
                slopes.append(float(beta[1]))
                firsts.append(float(G[0]))
                lasts.append(float(G[-1]))
        s = np.array(slopes)
        res["origin_nx%d" % nx] = {
            "n_origins": len(s),
            "slope_min": float(s.min()), "slope_max": float(s.max()),
            "slope_mean": float(s.mean()), "slope_sd": float(s.std(ddof=1)),
            "all_positive": bool((s > 0).all()),
            "G_first_min": float(min(firsts)), "G_first_max": float(max(firsts)),
            "G_last_min": float(min(lasts)), "G_last_max": float(max(lasts)),
        }
        print("[2] origin sweep, %d cells per side, %d origins" % (nx, len(s)))
        print("    uncorrected slope: %.4f to %.4f  (mean %.4f, sd %.4f)"
              % (s.min(), s.max(), s.mean(), s.std(ddof=1)))
        print("    all origins show a rise: %s" % bool((s > 0).all()))
        print("    2013 G range %.3f-%.3f ; 2026 G range %.3f-%.3f"
              % (min(firsts), max(firsts), min(lasts), max(lasts)))
        print()

    json.dump(res, open(here / "results_gridorigin.json", "w"), indent=1)
    print("wrote results_gridorigin.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
