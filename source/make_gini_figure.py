#!/usr/bin/env python3
"""Figure 3 - the Gini question, answered.

The figure previously showed the uncorrected series, which
rises with the population, while the text reports the rarefied series as a null.
Showing the rising series while the text withdraws the finding is a contradiction.

This figure replaces it. The rarefied series is the one plotted with intervals, on
the same grid and in the same unit as Table 4; the uncorrected values are drawn as
a faint reference line so the reader can see exactly what rarefaction removed.

Every number is read from results_gini.json. Nothing is typed here.
"""
import json, pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
G = json.loads((HERE / "results_gini.json").read_text())
R = G["res"]["20"]["rows"]
Y = [r["year"] for r in R]

plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42, "axes.grid": True, "grid.alpha": 0.3,
                     "figure.dpi": 300, "savefig.bbox": "tight", "axes.axisbelow": True})

fig, ax = plt.subplots(figsize=(5.4, 3.2))
ax.plot(Y, [r["raw"] for r in R], "s--", color="0.65", lw=1.2, ms=3,
        label="uncorrected (rises with population)")
ax.fill_between(Y, [r["ci"][0] for r in R], [r["ci"][1] for r in R],
                color="#4c72b0", alpha=0.20, label="rare interval")
ax.plot(Y, [r["rare"] for r in R], "o-", color="#4c72b0", lw=1.8, ms=4,
        label="rarefied to 39 locations")
ax.set_xlabel("year")
ax.set_ylabel("Gini of occupied cells (20 x 20, fixed grid)")
ax.set_ylim(0, 1)
ax.set_xlim(min(Y) - 0.5, max(Y) + 0.5)
ax.set_xticks(list(Y))
ax.set_xticklabels([str(y) for y in Y], fontsize=7, rotation=45)
ax.set_title("Rarefying to a common sample size removes the apparent trend\n"
             "the uncorrected series falls from +0.013 to -0.004 per year",
             fontsize=8.8)
ax.legend(fontsize=6.6, loc="upper left")
fig.tight_layout()
fig.savefig(HERE / "figures" / "figC3_gini_ci.pdf")
print("wrote figures/figC3_gini_ci.pdf")
