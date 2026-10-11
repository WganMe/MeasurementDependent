#!/usr/bin/env python3
"""Figure C1: the instrument population, with births and silences behind it.

Recovered from the scratch generator `make_census_figures.py`, which lived outside
this repository and also produced three figures that superseded per-figure
generators in this repository already replace (C2, C3, C6). Only the three
functions it alone produced are kept here: C1, C4 and C5. See
make_theme_drift_figure.py and make_theil_figure.py for the other two.

Everything is read from uo_census_results.json. No number is typed into this file.

Writes: figures/figC1_population.pdf
"""
from __future__ import annotations

import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

matplotlib.rcParams["pdf.fonttype"] = 42   # embed outlines, not Type 3 bitmaps

HERE = pathlib.Path(__file__).resolve().parent
D = json.loads((HERE / "uo_census_results.json").read_text())
OUT = HERE / "figures"
OUT.mkdir(exist_ok=True)

plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3,
                     "figure.dpi": 300, "savefig.bbox": "tight", "axes.axisbelow": True,
                     "axes.unicode_minus": False})

Y = [r["year"] for r in D["per_year"]]
N = [r["instruments"] for r in D["per_year"]]


def main() -> int:
    fig, ax = plt.subplots(figsize=(5.4, 3.1))
    ax.plot(Y, N, "o-", color="#4c72b0", lw=1.8, ms=4, label="instruments reporting")
    b = D["births_by_year"]
    s = D["silences_by_year"]
    ax.bar(Y, [b.get(str(y), 0) for y in Y], width=0.36, alpha=0.30,
           color="#55a868", label="first seen in this year")
    ax.bar(Y, [-s.get(str(y), 0) for y in Y], width=0.36, alpha=0.30,
           color="#c44e52", label="last seen in this year")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("year")
    ax.set_ylabel("instruments")
    ax.set_title("Instrument population 2013–2026: growth is churn, not a steady ramp",
                 fontsize=9)
    ax.legend(fontsize=6.6, loc="upper left")
    fig.savefig(OUT / "figC1_population.pdf")
    plt.close(fig)
    print("wrote figures/figC1_population.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
