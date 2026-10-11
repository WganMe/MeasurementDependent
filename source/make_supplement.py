#!/usr/bin/env python3
"""Build the Supplementary Material document (main_si.tex) from the result files.

The manuscript cites a supplementary file in eight places but no such file existed.
Every table here is generated from a `results_core_legacy*.json`, never typed, so the
supplement and the main text cannot drift apart.

Interpolation uses `{{TOKEN}}` replacement rather than `%` formatting, because LaTeX
text is full of literal `%` signs.

Usage:
    python3 make_supplement.py
Writes: main_si.tex
"""
from __future__ import annotations

import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent


def load(name):
    return json.loads((HERE / name).read_text())


def render(template: str, **kw) -> str:
    def sub(m):
        key = m.group(1)
        if key not in kw:
            raise KeyError("missing token %s" % key)
        return str(kw[key])
    return re.sub(r"\{\{([A-Za-z0-9_]+)\}\}", sub, template)


def f3(x):
    return "%.3f" % x


def pct(x):
    return "%.1f\\%%" % (100.0 * x)


def main() -> int:
    r4 = load("results_infill.json")
    r7 = load("results_rarefied.json")
    r8 = load("results_theilsen.json")
    r13 = load("results_multiscale.json")
    r13b = load("results_trendtests.json")
    r13c = load("results_inhomogeneous_ms.json")
    r13d = load("results_snapshot.json")
    r15 = load("results_envelope.json")
    r15b = load("results_exclusions.json")
    r15c = load("results_snapdupes.json")
    r16 = load("results_feeds.json")
    r16b = load("results_coredefs.json")
    r16c = load("results_thememde.json")
    r16d = load("results_gridorigin.json")
    r17 = load("results_thinning.json")
    xck = load("results_crosscheck.json")
    gini = load("results_gini.json")

    rs = [int(x) for x in r13["rs"]]
    RS14 = [float(x) for x in r13["rs"]]

    # ---------------------------------------------------------------- table bodies
    t_trend = "\n".join(
        r"%s & $%+.4f$ & %s & %s & %s & $[%+.3f, %+.3f]$ & %d \\"
        % (name, d["slope"], f3(d["ols_p"]), f3(d["perm_p"]), f3(d["mk_p"]),
           d["nw_ci"][0], d["nw_ci"][1], d["n"])
        for name, d in [("Hull $R$, locations", r13b["hull_loc"]),
                        ("Hull $R$, identifiers", r13b["hull_ids"]),
                        ("Hull $R$, locations, no 2026", r13b["hull_loc_no2026"]),
                        ("Hull $R$, locations, no 2017--18, 2026",
                         r13b["hull_loc_no_disc"])])

    t_size = "\n".join(
        r"AR(1) $\rho = %s$ & %s & %s \\"
        % (rho.split("_")[1], f3(r13b["size_sim"][rho]["nw_reject"]),
           f3(r13b["size_sim"][rho]["ols_reject"]))
        for rho in ("rho_0", "rho_0.15", "rho_0.3", "rho_0.5")) + "\n" + (
        r"i.i.d.\ Gaussian & --- & %s \\" % f3(r13b["size_sim"]["iid"]["ols_reject"]))

    t_anchor = "\n".join(
        r"%s & $%+.4f$ & %s & %s & %s \\"
        % (name, d["slope"], f3(d["ols_p"]), f3(d["perm_p"]), f3(d["mk_p"]))
        for name, d in [("Rarefied Gini, all fourteen years", r13b["gini_rare_full"]),
                        ("Rarefied Gini, 2013 anchor dropped", r13b["gini_rare_no2013"]),
                        ("Rarefied Gini, 2013 and 2026 dropped",
                         r13b["gini_rare_no2013_2026"])])

    t_gini_grid = "\n".join(
        r"%s & $%+.4f$ & $[%+.4f, %+.4f]$ & $%+.4f$ & %.0f \\"
        % (nx, gini["res"][nx]["rare_trend"]["slope"],
           gini["res"][nx]["rare_trend"]["theil_sen_ci"][0],
           gini["res"][nx]["rare_trend"]["theil_sen_ci"][1],
           gini["res"][nx]["raw_trend"]["slope"], gini["res"][nx]["cell_m"])
        for nx in ("20", "30", "40", "50"))

    t_infill_ratios = "\n".join(
        r"%d & %d & %s & %s & %s \\"
        % (r["year"], r["n_new"], f3(r["ratio_box"]), f3(r["ratio_core"]),
           f3(r["ratio_kde"]))
        for r in r4["A_infill"])

    t_infill_rl = "\n".join(
        r"%d & %d & %.0f & $[%.0f, %.0f]$ & %s \\"
        % (r["year"], r["n_new"], r["obs_median_m"], r["env_lo"], r["env_hi"],
           "above" if r["obs_median_m"] > r["env_hi"] else "inside")
        for r in r7["R7.6_random_labelling"]["rows"])

    t_lctrl = "\n".join([
        r"CSR, border correction & " + " & ".join("%+.1f" % v for v in r13["controls"]["csr"]) + r" \\",
        r"CSR, rectangular weight & " + " & ".join("%+.1f" % v for v in r13["control_old_estimator"]) + r" \\",
        r"Clustered & " + " & ".join("%+.1f" % v for v in r13["controls"]["clustered"]) + r" \\",
        r"Regular lattice & " + " & ".join("%+.1f" % v for v in r13["controls"]["regular"]) + r" \\",
    ])

    t_lnull = "\n".join(
        r"%s m & %d & %d & %d \\" % (k, v["above"], v["within"], v["below"])
        for k, v in r13c["vs_inhomogeneous"].items())

    t_lshape = "\n".join(
        r"%s & " % y + " & ".join("%+.2f" % v for v in r13c["normalised"][y]) + r" \\"
        for y in ("2013", "2017", "2020", "2023", "2026") if y in r13c["normalised"])

    veh = r13d["vehicle"]

    r14 = load("results_edge.json")
    r14t = load("results_themes.json")

    t_edge = "\n".join(
        r"%d & %.3f & %.3f & %.3f & %.3f \\"
        % (y, r14["edge"]["plain"][i], r14["edge"]["inside"][i],
           r14["edge"]["border"][i], r14["edge"]["guard500"][i])
        for i, y in enumerate(r14["years"]))

    t_edge_trend = "\n".join(
        r"%s & $%+.4f$ & $[%+.4f, %+.4f]$ & %s & %s \\"
        % (nm, r14["edge"]["trend"][k]["slope"], r14["edge"]["trend"][k]["nw_ci"][0],
           r14["edge"]["trend"][k]["nw_ci"][1],
           f3(r14["edge"]["trend"][k]["ols_p"]), f3(r14["edge"]["trend"][k]["mk_p"]))
        for k, nm in (("plain", "Headline (no correction)"),
                      ("inside", "Strictly inside the hull"),
                      ("border", "Ripley border correction"),
                      ("guard500", "Fixed 500 m guard area")))
    # crosscheck_donnelly.R (spatstat 3.8.3, R 4.6.1) writes results_donnelly_cdf.json.
    # spatstat REFUSES Donnelly on a non-rectangular window; the cdf correction is the
    # general-region alternative and is the only one of these computed independently.
    rdon = load("results_donnelly_cdf.json")
    _ct = rdon["cdf_trend"]
    t_edge_trend += "\n" + (
        r"\textsf{spatstat} \texttt{cdf} correction & $%+.4f$ & $[%+.4f, %+.4f]$ & %s & --- \\"
        % (_ct["ols_slope"], _ct["nw_ci"][0], _ct["nw_ci"][1], f3(_ct["ols_p"])))

    # the cdf series year by year, so the correction is visible and not only its trend
    t_cdfseries = "\n".join(
        r"%d & %d & %.3f & %.3f & %+.3f \\"
        % (d["year"], d["n"], d["R_raw"], d["R_cdf"], d["R_cdf"] - d["R_raw"])
        for d in rdon["per_year"])

    t_ep = "\n".join(
        r"%s & $%+.4f$ & %s & $%+.4f$ & %s & %s \\"
        % (nm, d["with_2026"]["slope"], f3(d["with_2026"]["ols_p"]),
           d["to_2025"]["slope"], f3(d["to_2025"]["ols_p"]),
           f3(d["to_2025"]["mk_p"]))
        for nm, d in (("Plain $R$", r14["endpoint"]["plain R"]),
                      ("Inside-hull $R$", r14["endpoint"]["inside R"]),
                      ("Border $R$", r14["endpoint"]["border R"]),
                      ("Guard-area $R$", r14["endpoint"]["guard R"])))

    t_theme = "\n".join(
        r"%s & $%+.4f$ & %s & %s & %d & %s \\"
        % (t, d["slope"], f3(d["ols_p"]), f3(d["mk_p"]), d["n"],
           ("%.4f" % r16c[t]["mde80"]) if t in r16c else "---")
        for t, d in sorted(r14t["themes"].items(), key=lambda kv: kv[1]["slope"]))

    t_gapL = "\n".join(
        r"%d & %d & %d & %s & %s \\"
        % (r["year"], r["n_pub"], r["n_filled"],
           ("%.0f" % r["L_pub"][list(RS14).index(1000.0)]),
           ("%.0f" % r["L_filled"][list(RS14).index(1000.0)]))
        for r in r14["gapfilled_L"])
    # the fitted trend is a separate quantity from the levels in the table above;
    # both are read from the result file so the main text cannot drift from them.
    gflt = r14["gapfilled_L_trend"]
    t_gapL += "\n" + (r"\midrule" "\n"
                      r"\multicolumn{3}{l}{Trend on year, \SI{1}{\kilo\meter}} & "
                      r"\textbf{%.1f} & \textbf{%.1f} \\" "\n"
                      r"\multicolumn{5}{l}{metres per year, published against gap-filled roster} \\"
                      % (gflt["pub_1km_slope"], gflt["filled_1km_slope"]))

    # round-22: the near-duplicate test. Section 3.4 promises it; this is it.
    nd = load("results_neardup.json")
    nd0 = nd["per_tol"]["exact (published)"]
    nd5 = nd["per_tol"]["5 m"]
    nd10 = nd["per_tol"]["10 m"]
    nd25 = nd["per_tol"]["25 m"]

    def _ndrow(label, e):
        return (r"%s & %.3f & %.3f & %.1f\%% & $%+.4f$ & %s & $%+.1f$ \\"
                % (label, e["R_first"], e["R_last"], e["fall_pct"], e["slope"],
                   ("$<0.001$" if e["ols_p"] < 0.001 else "%.3f" % e["ols_p"]),
                   e["pooled"][-1]["z"]))

    t_nd = "\n".join([
        _ndrow("Exact coordinate (published)", nd0),
        _ndrow(r"Within \SI{5}{\meter}", nd5),
        _ndrow(r"Within \SI{10}{\meter}", nd10),
        _ndrow(r"Within \SI{25}{\meter}", nd25),
    ])
    t_ndmerge = "\n".join(
        r"%d & %d & %d & %d & %d & %d \\"
        % (r0["year"], r0["n_raw"], r5["n_sites"], r10["n_sites"], r25["n_sites"],
           r0["n_raw"] - r25["n_sites"])
        for r0, r5, r10, r25 in zip(nd0["rows"], nd5["rows"], nd10["rows"],
                                    nd25["rows"]))
    t_ndpooled = "\n".join(
        r"%d & %d & %.3f & %.3f & %.3f & $%+.2f$ \\"
        % (r["year"], r["n"], r["R_obs"], r["R_pooled"], r["sd"], r["z"])
        for r in nd25["pooled"])

    r7_rare = r7["R7.2_rarefied_R"]
    t_rare_r = "\n".join(
        r"%d & %.3f & %.3f & %.3f \\"
        % (y, r7_rare["rarefied"][i], r7_rare["full"][i],
           r7_rare["rarefied"][i] - r7_rare["full"][i])
        for i, y in enumerate(r13b["years"]))

    # -------------------------------------------------- round-15 tables
    # S8: the complete-spatial-randomness control as a draw rather than a value.
    env = r15["csr_envelope"]
    scales15 = [int(float(x)) for x in r15["rs"]]
    t_env = "\n".join(
        r"$%d$ & %.1f & %.1f & %.1f & %.1f \\"
        % (scales15[i],
           env["39"]["mean"][i], env["39"]["sd"][i],
           env["561"]["mean"][i], env["561"]["sd"][i])
        for i in range(len(scales15)))
    t_envbias = None
    t_envbias = r"Mean $|$bias$|$ (m) & %.1f & %.1f & %.1f \\" % (
        env["39"]["mean_abs_bias_m"], env["200"]["mean_abs_bias_m"],
        env["561"]["mean_abs_bias_m"])
    t_envbias += "\n" + r"Scatter, single realisation (m) & %.1f & %.1f & %.1f \\" % (
        env["39"]["mean_sd_m"], env["200"]["mean_sd_m"], env["561"]["mean_sd_m"])
    t_biasfrac = "\n".join(
        r"$%d$ & %.1f \\" % (int(float(k)), 100.0 * v)
        for k, v in sorted(r15["bias_fraction"].items(), key=lambda kv: float(kv[0])))
    t_loo = t_biasfrac and "\n".join(
        r"%d & %d & %.2f & %.1f \\"
        % (d["year"], d["n"], d["median_loo_R"], 100.0 * d["frac_below_1"])
        for d in r15["loo_intensity"])

    # S9: the snapshot's duplicate registrations and the multiscale exclusions.
    t_snapdup = "\n".join(
        r"%s & %d & %.1f \\" % (lab, r15c[k], 100.0 * r15c[k] / 179)
        for lab, k in (("Within 1 m", "within_1m"), ("Within 5 m", "within_5m"),
                       ("Within 10 m", "within_10m"), ("Within 25 m", "within_25m"),
                       ("Within 50 m", "within_50m"), ("Beyond 50 m", "beyond_50m")))
    ex = r15b["multiscale_exclusions"]
    t_excl = "\n".join([
        r"$L(500\,\mathrm{m})$ & %.1f & %.1f \\" % (ex["slope_all_500"], ex["slope_excl_500"]),
        r"$L(1000\,\mathrm{m})$ & %.1f & %.1f \\" % (ex["slope_all_1000"], ex["slope_excl_1000"]),
    ])
    inf = r15b["infill_exclusions"]
    t_inflexcl = r"All years & %d & %d \\" % (inf["n_above"], inf["n"])
    t_inflexcl += "\n" + (r"Excluding 2017--2018, 2026 & %d & %d \\"
                          % (inf["n_above_sub"], inf["n_sub"]))

    # ------------------------------------------------ round-16 provenance detail
    # `broker_name` stands in for theme: the snapshot stores no theme field, and
    # the broker is the feed the archive's own theme directories are built from.
    rb = r16["reading_bearing"]
    esc = lambda s: s.replace("_", "\\_")
    t_rbbroker = "\n".join(r"%s & %d & %.1f \\" % (esc(b), n, 100.0 * n / rb["n"])
                           for b, n in rb["broker_mix"])
    t_snapbroker = "\n".join(
        r"%s & %d & %.1f & %d & %.1f \\"
        % (esc(b), n, 100.0 * n / r16["snapshot_only"],
           dict(r16["broker_mix_matched"]).get(b, 0),
           100.0 * dict(r16["broker_mix_matched"]).get(b, 0) / r16["matched"])
        for b, n in r16["broker_mix_snapshot_only"][:8])

    # round-16b: the core rectangle is a chosen support, so sweep it
    lbl = {"trim_p1": "Trim 1st--99th pct", "trim_p2.5": "Trim 2.5th--97.5th pct",
           "trim_p5": "Trim 5th--95th pct (headline)", "trim_p10": "Trim 10th--90th pct",
           "trim_p25": "Trim 25th--75th pct",
           "hull_central80": "Convex hull, central 80\\%",
           "disc_2km": "Fixed \\SI{2}{\\kilo\\meter} disc",
           "disc_3km": "Fixed \\SI{3}{\\kilo\\meter} disc",
           "disc_5km": "Fixed \\SI{5}{\\kilo\\meter} disc"}
    t_core = "\n".join(
        r"%s & %.3f & %.3f & %+.4f & %s \\"
        % (lbl.get(k, k), v["R_first"], v["R_last"], v["slope"],
           ("$<0.001$" if v["p"] < 0.001 else f3(v["p"])))
        for k, v in r16b["sweeps"].items())

    # round-16d: the grid origin is a choice too
    t_origin = "\n".join(
        r"%d & %.4f--%.4f & %.4f & %.4f & %s \\"
        % (nx, v["slope_min"], v["slope_max"], v["slope_mean"], v["slope_sd"],
           ("yes" if v["all_positive"] else "no"))
        for nx, v in sorted(
            ((int(k.split("nx")[1]), vv) for k, vv in r16d.items() if k.startswith("origin_nx")),
            key=lambda kv: kv[0]))

    # round-17 cross-check: the manuscript's estimator against spatstat 3.8.3
    t_xck = "\n".join(
        r"%s & %.3f & %.3f \\" % (k, v["median_pct"], v["max_pct"])
        for k, v in sorted(xck["per_scale"].items(), key=lambda kv: int(kv[0])))
    # round-17: the POOLED reference, which can judge every year
    t_pooled = "\n".join(
        r"%d & %d & %.3f & %.3f & %.3f & $%+.2f$ \\"
        % (r["year"], r["n"], r["R_obs"], r["R_pooled"], r["sd"], r["z"])
        for r in r17["vs_pooled"])

    # round-17: the thinning-invariance test
    t_thin = "\n".join(
        r"%d & %d & %.3f & %.3f & %+.3f \\"
        % (r["year"], r["n"], r["R_obs"], r["R_thinned_ref"], r["excess"])
        for r in r17["vs_thinned_2026"])

    DOC = r"""%=================================================================
%  Supplementary Material
%  A supplement to: "Measurement-Dependent Clustering in the Growing Urban
%   Observatory Sensor Network"
%
%  This header once carried an earlier working title. It is deliberately not
%  repeated here: a superseded title in a source file is indistinguishable from
%  the current one to anyone reading the archive, and it shipped in a bundle.
%  The authoritative title is the \Title below, which matches main.tex.
%
%  GENERATED by make_supplement.py from the results_core_legacy*.json files.
%  Do not edit by hand: rebuild with `python3 make_supplement.py`.
%=================================================================
\documentclass{article}
\usepackage{amsmath}
\usepackage{siunitx}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{float}
% natbib and a bibliography, because the supplement now CITES: it names Ripley's border
% correction, Donnelly's correction and spatstat (the cross-check it rests on is a spatstat
% run). An uncited name is a reader-visible gap, and the supplement is published as its own
% file, so a reader who downloads only this document needs the references here rather than
% having to find the main text.
\usepackage[authoryear]{natbib}
\bibliographystyle{plainnat}
\providecommand{\doi}[1]{\href{https://doi.org/#1}{\nolinkurl{#1}}}
\usepackage[hidelinks]{hyperref}
\usepackage{url}
\graphicspath{{figures/}}

%% Front-matter macros, defined here rather than taken from a journal class: this
%% source carries no venue, and convert_to_peerj.py rebuilds the title block for PeerJ.
\newcommand{\Title}[1]{\title{#1}\def\theTitle{#1}}
\newcommand{\Author}[1]{\author{#1}\def\theAuthor{#1}}
\newcommand{\AuthorNames}[1]{\def\theAuthorNames{#1}}
\newcommand{\corres}[1]{\def\theCorres{#1}}
\newcommand{\address}[1]{\def\theAddress{#1}}
\newcommand{\firstpage}[1]{\def\theFirstpage{#1}}
\newcommand{\pubvolume}[1]{}
\newcommand{\issuenum}[1]{}
\newcommand{\articlenumber}[1]{}
\newcommand{\pubyear}[1]{}
\newcommand{\copyrightyear}[1]{}
\newcommand{\datereceived}[1]{}
\newcommand{\daterevised}[1]{}
\newcommand{\dateaccepted}[1]{}
\newcommand{\datepublished}[1]{}
\newcommand{\keyword}[1]{\def\theKeyword{#1}}
\newcommand{\reftitle}[1]{}

\Title{Supplementary Material: Measurement-Dependent Clustering in the Growing Urban Observatory
Sensor Network}
% SAME AUTHOR ORDER AS THE MANUSCRIPT: Arbaaeen first. The supplement is a separate file
% that a reader may open alone, so an order here that disagreed with the byline would be a
% second, contradictory statement of authorship. \AuthorNames is the running short form and
% must name whoever is now FIRST, not whoever was first before the reorder.
\Author{Ammar Arbaaeen, Wael Alnahari, Ammar Alsaig, Tawfiq Hasanin and Wasem Alnahri}
\AuthorNames{Arbaaeen et al.}
\corres{Correspondence: walnahari0004@stu.kau.edu.sa}
\address{%
$^{1}$~\quad Department of Information Systems, Faculty of Computing and Information
Technology, King Abdulaziz University, Jeddah 21589, Saudi Arabia\\
$^{2}$~\quad Department of Computer Science, College of Computer and Information
Systems, Umm Al-Qura University, Mecca 24381, Saudi Arabia\\
$^{3}$~\quad Independent Researcher, Mecca 24331, Saudi Arabia}

\firstpage{1}
\pubvolume{1}
\issuenum{1}
\articlenumber{0}
\pubyear{2027}
\copyrightyear{2027}
\datereceived{ }
\daterevised{ }
\dateaccepted{ }
\datepublished{ }

\begin{document}
\maketitle

% Number sections and tables with an S prefix so the main text's pointers ("Section S5",
% "Table S3") resolve unambiguously against this document.
\renewcommand{\thesection}{S\arabic{section}}
\renewcommand{\thetable}{S\arabic{table}}
\renewcommand{\theequation}{S\arabic{equation}}

\noindent This supplement carries the robustness forks, sensitivity sweeps and estimator
controls that the main text summarises but does not tabulate. Sections are numbered with an
S prefix, and tables with the same, so a main-text pointer resolves against this document
without translation. Section~S1 gives the trend tests
under every interval procedure; S2 every procedure named in the main text with the value it
returns on the headline series; S3 the rarefaction and its anchor sensitivity; S4 the
multiscale estimator and its known-answer controls; S5 the reference-frame and grid sweeps;
S6 the edge-corrected clustering, the \texttt{cdf} correction and the endpoint check; S7 the
theme-stratified trend; S8 the gap-filled sensitivity for the multiscale function and the
infill test; S9 the infill diagnostics; S10 the snapshot audit in full; S11 the
clustering control as a draw and the leave-one-out intensity check; S12 the snapshot's duplicate
registrations and two exclusion sweeps; S13 what the snapshot actually contains by ingestion
feed; S14 the core-definition sensitivity; S15 the grid-origin sensitivity for the concentration
index; S16 the independent cross-check against \textsf{spatstat}; S17 the thinning-invariance
test; S18 the near-duplicate test that qualifies the headline decline; and S19 the multiplicity
count, the per-year-pair clustering test with its false-discovery correction, the seed check and
the code
inventory. Every
table is generated from the analysis result files by
\texttt{make\_supplement.py}, so the numbers here and in the main text share one source.

\section{Trend tests under each interval procedure}
\label{si:inference}

The main text rests the fixed-hull decline on the three tests that are correctly sized at
fourteen points. The HAC family is reported here, with its own size. Simulating the
OLS-plus-Newey--West statistic at $n = 14$ on pure noise with a $t(12)$ critical value rejects
at a nominal 5\% about {{SZ0}} of the time, and about {{SZ3}} of the time at the lag-1
autocorrelation the headline series actually shows, so the test is anti-conservative at this sample size. That is why it is
not the primary evidence.

\begin{table}[H]
\centering
\caption{The clustering trend on the fixed hull under each procedure. The OLS and permutation $p$-columns are nominal.}
\label{si:trend}
\footnotesize
\setlength{\tabcolsep}{4pt}
\begin{tabular}{lrrrrrr}
\toprule
Series & Slope/yr & OLS & Perm. & M--K & NW interval & $n$ \\
\midrule
{{TREND}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{Size of the OLS-plus-Newey--West test at $n = 14$ with a $t(12)$ critical value,
simulated on series with no trend. A correctly sized test rejects at the nominal rate.}
\label{si:size}
\small
\begin{tabular}{lrr}
\toprule
Error process & Newey--West rejects & OLS rejects \\
\midrule
{{SIZE}}
\bottomrule
\end{tabular}
\end{table}

\section{Every procedure named in the text, with its value}
\label{si:procedures}

The main text names a family of inference procedures and reports the intervals they give. This
table puts them side by side on the series that carry the result, so that a reader can see which
procedure is responsible for which claim, and can tell a disagreement between procedures from a
disagreement between studies. The size simulation at the foot is the check that the HAC interval
is not merely narrower than the others: at fourteen points neither the OLS nor the HAC test
attains its nominal size.

\begin{table}[H]
\centering
\caption{Every inference procedure named in the main text, on the headline series and the
rarefied one. ``Contains 0'' records whether the interval spans zero.}
\label{si:procs}
\footnotesize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{p{3.3cm}rrrp{1.4cm}}
\toprule
Procedure & \multicolumn{1}{p{1.6cm}}{Hull $R$, locs} & \multicolumn{1}{p{1.6cm}}{Hull $R$, ids} & \multicolumn{1}{p{1.6cm}}{Rarefied $R$} & Contains 0 \\
\midrule
OLS slope & $-0.01071$ & $-0.01257$ & $+0.00031$ & no / no / yes \\
OLS interval ($t_{12}$) & $[-0.0207,-0.0008]$ & $[-0.0226,-0.0025]$ & $[-0.0047,+0.0053]$ & no / no / yes \\
Permutation & $0.038$ & $0.020$ & --- & --- \\
Mann--Kendall & $0.010$ & $0.010$ & --- & --- \\
Newey--West (HAC, lag 2) & $[-0.0188,-0.0027]$ & $[-0.0213,-0.0039]$ & $[-0.0045,+0.0052]$ & no / no / yes \\
Theil--Sen & $-0.00955$ & $-0.01461$ & $-0.00017$ & no / no / yes \\
Theil--Sen interval & $[-0.0217,-0.0047]$ & $[-0.0278,-0.0047]$ & $[-0.0045,+0.0062]$ & no / no / yes \\
Moving-block bootstrap (box) & $[-0.578,-0.305]$ & --- & --- & no \\
Prais--Winsten & $-0.0754$ & --- & --- & no \\
Fixed-$b$ (Kiefer--Vogelsang) & $[-0.1017,-0.0509]$ & --- & --- & no \\
TOST, full margin & $p = 1.8\times10^{-9}$ & --- & --- & equivalent \\
TOST, half margin & $p = 3.9\times10^{-6}$ & --- & --- & equivalent \\
Power at \SI{80}{\percent} & \multicolumn{3}{c}{$0.99999$ for a change of the raw size} & --- \\
\midrule
Size of the \SI{5}{\percent} test (simulated) & \multicolumn{3}{c}{$\rho = 0$: OLS $0.049$, HAC $0.163$; $\rho = 0.5$: OLS $0.217$, HAC $0.294$} & --- \\
\bottomrule
\end{tabular}
\end{table}

\noindent Every procedure agrees in sign. The OLS test is correctly sized in the same
simulation, rejecting \SI{4.7}{\percent} under independent errors, but it is mildly optimistic
once the errors are autocorrelated: \SI{8.5}{\percent} at the lag-1 residual autocorrelation the
fixed-hull series has ($+0.15$) and \SI{21.8}{\percent} at $\rho = 0.5$. The HAC test is
anti-conservative throughout, \SI{16.3}{\percent} under independence and \SI{29.4}{\percent} at
$\rho = 0.5$, so it is not a safe substitute for the OLS test at this length. Because no single $p$-value here is calibrated for every error process, the main
text carries each claim on more than one procedure and reports the split rather than the
strongest interval.

\section{Rarefaction and the anchor sensitivity}
\label{si:rarefy}

Rarefying every year to a common sample size removes the trend in the clustering index and in
the concentration index alike. Table~\ref{si:anchor} is the anchor test: the anchor year's
rarefied value equals its raw value by construction and therefore carries unusual leverage, and
dropping it shows whether the residual slope belongs to the rarefaction or to the anchor.
Table~\ref{si:scale} states the scale the rarefied index can resolve, which is the bound on
what the main text may conclude from it.

\begin{table}[H]
\centering
\caption{Rarefied concentration index and the anchor sensitivity.}
\label{si:anchor}
\small
\begin{tabular}{lrrrr}
\toprule
Series & Slope/yr & OLS $p$ & Perm.\ $p$ & M--K $p$ \\
\midrule
{{ANCHOR}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{The rarefied clustering index year by year, with the unrarefied series for
comparison. Neither rarefied series has a trend.}
\label{si:rarer}
\small
\begin{tabular}{lrrr}
\toprule
Year & Rarefied $R$ & Unrarefied $R$ & Difference \\
\midrule
{{RARER}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{The scale the rarefied index can resolve. At the smallest year's sample size the
expected nearest-neighbour distance under the reference density is a substantial fraction of the
network's own extent.}
\label{si:scale}
\small
\begin{tabular}{lr}
\toprule
Quantity & Value \\
\midrule
Rarefaction sample size (identifiers) & {{NMIN}} \\
Hull area (km$^2$) & {{HULLKM}} \\
Expected nearest-neighbour distance (m) & {{ENN}} \\
Location sample size, smallest year & {{LOCMIN}} \\
Anchor sizes tested for the concentration index & 39, 150, 200 \\
\bottomrule
\end{tabular}
\end{table}

\section{The multiscale estimator and its controls}
\label{si:lcurve}

The multiscale function is computed on the convex hull of the full record, and a hull is not a
rectangle. A translational edge weight $(1-d_x/a)(1-d_y/b)$ is valid only for a rectangular
window, and applied to a hull it biases the curve. Table~\ref{si:lcontrol} is the known-answer
control for the estimator's own convention: on a complete-spatial-randomness pattern, where $L$ is zero by
definition, the rectangular weight returns a large spurious value while the border correction
returns a value near zero. ``Near'' is not ``zero'', and the difference is the subject of
Section~\ref{si:envelope}: the control is itself a draw, so it carries sampling scatter, and the
residual left after averaging is the bias of the estimator. Over \num{199} realisations that
residual has a mean absolute value of \SI{262.7}{\meter} at $N = 39$, \SI{33.3}{\meter} at
$N = 200$ and \SI{4.1}{\meter} at $N = 561$ (Table~\ref{si:envbias}). The correction is therefore
adequate at the sample sizes of the later years and weakly biased in the earliest, sparsest year,
which is why the multiscale claims are made for the scale range where the separation is unanimous
and not for every scale examined.

\begin{table}[H]
\centering
\caption{Known-answer control for the multiscale estimator. A complete-spatial-randomness
pattern inside the hull must return $L = 0$ at every scale.}
\label{si:lcontrol}
\footnotesize
\setlength{\tabcolsep}{4pt}
\begin{tabular}{l{{RSCOLS}}}
\toprule
Pattern & {{RSHEAD}} \\
\midrule
{{LCTRL}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{The multiscale function against an inhomogeneous null, on
deduplicated locations. Each cell counts years, of fourteen, in each position.}
\label{si:lnull}
\small
\begin{tabular}{lrrr}
\toprule
Scale & Above null & Inside & Below \\
\midrule
{{LNULL}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{Curve shape, each year's multiscale function normalised by its own
\SI{2}{\kilo\meter} value so that the window's effect on the level cancels.}
\label{si:lshape}
\footnotesize
\setlength{\tabcolsep}{4pt}
\begin{tabular}{l{{RSCOLS}}}
\toprule
Year & {{RSHEAD}} \\
\midrule
{{LSHAPE}}
\bottomrule
\end{tabular}
\end{table}

\section{Reference frames, units and the rarefaction grid}
\label{si:frames}

The clustering index is sensitive to the area in its denominator and the concentration index to
the grid. The main text reports the headline frame and unit; the sweep is here.

\begin{table}[H]
\centering
\caption{Rarefied concentration index at four grid resolutions. Rarefaction reverses the sign of the slope rather than only flattening the series.}
\label{si:ginigrid}
\small
\begin{tabular}{lrrrr}
\toprule
Cells per side & Rarefied slope & Theil--Sen interval & Uncorrected slope & Cell (m) \\
\midrule
{{GINIGRID}}
\bottomrule
\end{tabular}
\end{table}

\section{Edge-corrected clustering and the 2026 endpoint}
\label{si:edge}

The headline Clark--Evans $R$ is uncorrected for edge bias, and in a longitudinal study both
$N$ and the spatial extent move, so edge bias could itself trend. Table~\ref{si:edgeest} gives
four edge estimators on the fixed hull and \ref{si:edgetrend} their trends, and the trend table
adds a fifth computed with an independent implementation. The first is the
headline estimator with no correction; the second keeps only points strictly inside the hull,
which drops the handful of sites lying exactly on it; the third is Ripley's border correction
\citep{ripley1977modelling},
using each point's own nearest-neighbour distance as its guard width; the fourth uses a fixed
\SI{500}{\meter} guard area. All five decline, with slopes between $-0.0107$ and $-0.0159$ per
year, so edge bias does not drive the trend. The border estimator carries its own small bias:
on complete-spatial-randomness controls it returns $0.90$ at $n = 100$ and $0.98$ at $n = 700$,
so it is reported as a sensitivity and not as the headline.

A fifth estimator is in Table~\ref{si:edgetrend} because it is the only one computed with an
independent implementation. Donnelly's correction \citep{donnelly1978simulations} is written in
terms of the window's area and
perimeter, both of which a hull has, but \textsf{spatstat} \citep{baddeley2005spatstat} refuses it
on any non-rectangular
window, reporting that it is \emph{only available for rectangular windows}, because Donnelly's
coefficients were estimated by simulation on rectangles. Its \texttt{cdf} correction makes no
for random points drawn in the \emph{same} window. On our hull and points that correction gives
a 2013--2026 fall of \SI{57.2}{\percent} against \SI{45.0}{\percent} for the raw index, and a
steeper fitted slope, so the general-region correction steepens the uncorrected series. It does
not touch the question the tolerance test raises, because co-location is a question about which
records are one unit rather than about the window edge. On complete-spatial-randomness controls in the same hull it returns $0.992$ at
$n = 500$ where the raw index returns $1.015$, so it is the better centred of the two on
randomness as well. Donnelly's own area-and-perimeter form is stable on the same control here
--- \num{1.00} $\pm$ \num{0.07} at $n = 50$ tightening to \num{1.00} $\pm$ \num{0.01} at
$n = 2000$ --- but since the reference implementation declines to apply it to a polygon we report
the \texttt{cdf} correction as the external check. Every corrected series falls, but they do not
agree on the magnitude: \texttt{cdf} steepens the uncorrected series ($57.2\%$ against $45.0\%$),
while Donnelly flattens it to $41.9\%$ ($0.341$ to $0.198$), a smaller fall than the raw index
rather than a larger one. The direction is robust to the edge treatment; the magnitude is not.

\begin{table}[H]
\centering
\caption{Clark--Evans $R$ on the fixed hull under four edge treatments, locations.}
\label{si:edgeest}
\footnotesize
\setlength{\tabcolsep}{4pt}
\begin{tabular}{lrrrr}
\toprule
Year & Plain & Strictly inside & Border corrected & 500 m guard \\
\midrule
{{EDGE}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{Trend in each edge treatment. The four corrected series exclude zero on Newey--West, OLS and Mann--Kendall.}
\label{si:edgetrend}
\small
\begin{tabular}{lrrrr}
\toprule
Estimator & Slope/yr & Newey--West interval & OLS $p$ & M--K $p$ \\
\midrule
{{EDGETREND}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{The \textsf{spatstat} \texttt{cdf}-corrected Clark--Evans series year by year, against
the raw index on the same points and window. This is the only series in the paper computed with
an independent implementation.}
\label{si:cdfseries}
\small
\begin{tabular}{lrrrr}
\toprule
Year & Locations & Raw $R$ & \texttt{cdf} $R$ & Difference \\
\midrule
{{CDFSERIES}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{The 2026 endpoint. 2026 is a nine-month partial year, so every headline quantity is
reported with it and with 2025 as the last year.}
\label{si:endpoint}
\small
\begin{tabular}{lrrrrr}
\toprule
Series & Slope to 2026 & OLS $p$ & Slope to 2025 & OLS $p$ & M--K $p$ \\
\midrule
{{EP}}
\bottomrule
\end{tabular}
\end{table}

\section{Theme composition as a confounder}
\label{si:theme}

Vehicle share ranges from 58.5\% to 73.0\% on identifiers across the record and collapses to
16.8\% in 2018 on the same basis,
so the pooled clustering trend could be a composition effect. Table~\ref{si:themetab} fits the
trend separately within each theme, and the result is that no single theme drives it: the
pooled slope is $-0.0107$ per year, the vehicle theme alone falls at $-0.0122$ (OLS $p = 0.31$,
Mann--Kendall $p = 0.014$), and the themes that grow are small. The composition therefore
contributes to the magnitude but does not create the direction.

The last column is what a within-theme null is worth, and it is less than it appears. Each
theme is fitted on its own, so each has its own year count and scatter; the minimum detectable
effect at \SI{80}{\percent} power is larger than the pooled slope for \emph{all seven} themes:
the smallest is Air Quality at \num{0.023} per year and the largest is Sensor Metrics at
\num{0.182}, against a pooled slope of \num{0.011}. No theme's own series can resolve an effect
of the pooled size, so none of the seven within-theme nulls is evidence of uniformity. The vehicle theme is the instructive case:
at \num{0.035} per year its threshold is three times the pooled slope of \num{0.011}, so its
non-significant result is an absence of evidence rather than evidence of absence. This does not
weaken the pooled finding, which is carried by the whole record, but it does mean the theme
panel cannot support the stronger claim that no subset shows the trend.

\begin{table}[H]
\centering
\caption{Clustering trend within each theme, on deduplicated locations. The pooled series is
$-0.0107$ per year for comparison. Minimum detectable effect is at \SI{80}{\percent} power on
that theme's own year count.}
\label{si:themetab}
\small
\begin{tabular}{lrrrrr}
\toprule
Theme & Slope/yr & OLS $p$ & M--K $p$ & Years & MDE$_{80}$ \\
\midrule
{{THEME}}
\bottomrule
\end{tabular}
\end{table}

\section{Gap-filled sensitivity for the multiscale function and the infill test}
\label{si:gapfill}

The gap-filled roster is the sensitivity for the published record, since a silent instrument is
indistinguishable from a decommissioned one. The main text reports it for $R$ and the
concentration index; Table~\ref{si:gapL} extends it to the multiscale function and the infill
test. The multiscale decline is present on the gap-filled roster as well, and the infill count
is unchanged at 12 of 13 year pairs above the envelope. The separate exclusion sweep, which
drops the discontinuity years rather than filling their gaps, is a different check and does
change the count; it is reported in Section~\ref{si:dup}.

\begin{table}[H]
\centering
\caption{The multiscale function at \SI{1}{\kilo\meter}, published roster against gap-filled
roster, with the location count each uses.}
\label{si:gapL}
\small
\begin{tabular}{lrrrr}
\toprule
Year & $n$ published & $n$ gap-filled & $L(1\,\mathrm{km})$ published & gap-filled \\
\midrule
{{GAPL}}
\bottomrule
\end{tabular}
\end{table}

\section{Infill diagnostics}
\label{si:infill}

The homogeneous reference regions are reported here as an alternative to the random-labelling
test. All three depend on a homogeneous reference region and so repeat the confound they were meant to
remove; they are recorded here for completeness and are not used as evidence.

\begin{table}[H]
\centering
\caption{Distance ratios against three homogeneous reference regions, every year pair. A ratio
below one reads as infill and above one as expansion; the three do not agree.}
\label{si:infillratios}
\small
\begin{tabular}{lrrrr}
\toprule
Year & New locations & Ratio to box & Ratio to core & Ratio to kernel density \\
\midrule
{{INFILLRATIOS}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{The random-labelling infill test, all thirteen year pairs.}
\label{si:infillrl}
\small
\begin{tabular}{lrrrr}
\toprule
Year & New locations & Observed median (m) & Permutation envelope (m) & Position \\
\midrule
{{INFILLRL}}
\bottomrule
\end{tabular}
\end{table}

\section{The snapshot audit in full}
\label{si:snapshot}

The audited snapshot was prepared by the present authors for a separate benchmarking study. Its
coverage of the whole census is 64.9\%, but that figure mixes two different populations, because
the snapshot is a catalogue drawn in 2026 and the census spans every year from 2013. Of the
identifiers the two hold in common, only 440 were still reporting in 2026: the rest are retired
instruments that the snapshot nevertheless contains, so it is not a current-instrument list.
The comparison that isolates the omission is the like-for-like one, against the identifiers
active in the snapshot's own year, which is 62.3\%.

\begin{table}[H]
\centering
\caption{The snapshot against the census, unconditioned and conditioned on the snapshot's own
year.}
\label{si:snap}
\small
\begin{tabular}{lr}
\toprule
Quantity & Value \\
\midrule
Bundle created & {{CREATED}} \\
Readings window & {{WINLO}} to {{WINHI}} \\
Snapshot identifiers & {{SNAPID}} \\
Identifiers with any reading & {{SNAPREAD}} \\
Census identifiers & {{CENSUS}} \\
Matched & {{MATCHED}} \\
Snapshot-only & {{ONLYSNAP}} \\
Census-only & {{ONLYCENSUS}} \\
Coverage of the census & {{COVGEO}} \\
Census identifiers active in 2026 & {{ACT26}} \\
\quad of those in the snapshot & {{ACT26IN}} \\
\quad omitted & {{ACT26OUT}} \\
Coverage conditioned on 2026 & {{COV26}} \\
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{Vehicle contrast, conditioned on identifiers active in the snapshot's own year.}
\label{si:veh}
\small
\begin{tabular}{lrrr}
\toprule
 & Vehicles & Non-vehicles & Vehicle share \\
\midrule
Omitted (2026-conditioned) & {{OMVEH}} & {{OMOTH}} & {{OMSHARE}} \\
Matched (2026-conditioned) & {{INVEH}} & {{INOTH}} & {{INSHARE}} \\
\midrule
\multicolumn{4}{l}{Odds ratio {{OR}}; Fisher exact $p = {{FISHER}}$} \\
\bottomrule
\end{tabular}
\end{table}

\section{The clustering control as a draw, not a value}
\label{si:envelope}
A single complete-spatial-randomness realisation is not a null value: the control is itself a
draw, so it carries sampling scatter, and any residual left after averaging is the bias of the
estimator rather than noise. Table~\ref{si:env} gives the control at three sample sizes over
{{NRUN}} realisations, and Table~\ref{si:envbias} separates the two components at each size.
The distinction matters because a control that is averaged is often described as sitting on
zero when it in fact sits a few metres off it.

\begin{table}[H]
\centering
\caption{Border-corrected multiscale $L$ under complete spatial randomness, 199 realisations at each sample size. A negative mean is the estimator's bias, quantified in Table~\ref{si:envbias}.}
\label{si:env}
\small
\begin{tabular}{lrrrr}
\toprule
 & \multicolumn{2}{c}{$N = 39$} & \multicolumn{2}{c}{$N = 561$} \\
\cmidrule(lr){2-3}\cmidrule(lr){4-5}
Scale & Mean & SD & Mean & SD \\
\midrule
{{ENVBODY}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{The two components of the control at each sample size, pooled over scales:
the residual mean absolute bias of the estimator, and the scatter of a single realisation.}
\label{si:envbias}
\small
\begin{tabular}{lrrr}
\toprule
 & $N = 39$ & $N = 200$ & $N = 561$ \\
\midrule
{{ENVBIAS}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{Residual bias of the control as a fraction of the observed signal, by scale.}
\label{si:envfrac}
\small
\begin{tabular}{lr}
\toprule
Scale (m) & Bias as share of observed $L$ (\%) \\
\midrule
{{BIASFRAC}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{Leave-one-out intensity: each location's nearest-neighbour distance divided by the distance the leave-one-out kernel density predicts for it ($h = \SI{750}{\meter}$, all other points).}
\label{si:loo}
\small
\begin{tabular}{lrrr}
\toprule
Year & $N$ & Median ratio & Share below 1 \\
\midrule
{{LOOBODY}}
\bottomrule
\end{tabular}
\end{table}

\section{The snapshot's duplicate registrations and two exclusion sweeps}
\label{si:dup}

The snapshot holds {{SNAPDUPN}} identifiers absent from the census. Matched by position rather
than by identifier, most of them are re-registrations of sites the census already holds, so the
raw set difference overstates the disagreement between the two artefacts. Table~\ref{si:snapdist}
gives the resolution.

\begin{table}[H]
\centering
\caption{The snapshot-only identifiers resolved to the nearest location in the census.}
\label{si:snapdist}
\small
\begin{tabular}{lrr}
\toprule
Distance to nearest census location & Identifiers & Share of {{SNAPDUPN}} \\
\midrule
{{SNAPDUPBODY}}
\bottomrule
\end{tabular}
\end{table}

Two further exclusions test whether the headline multiscale and infill results depend on the
years with a known publishing discontinuity. Table~\ref{si:excl} refits the multiscale trend with
the 2017--2018 and 2026 years removed, and reports the infill count on the same subset.

\begin{table}[H]
\centering
\caption{Multiscale trend with and without the discontinuity years, on deduplicated locations.}
\label{si:excl}
\small
\begin{tabular}{lrr}
\toprule
Series & All years & Excluding 2017--2018, 2026 \\
\midrule
{{EXCLBODY}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{Infill test: observed medians above the permutation envelope.}
\label{si:inflexcl}
\small
\begin{tabular}{lrr}
\toprule
 & Year pairs above envelope & Year pairs tested \\
\midrule
{{INFLEXCL}}
\bottomrule
\end{tabular}
\end{table}

The minimum detectable effect for the rarefied concentration slope is
{{GINIMDE}} per year at \SI{80}{\percent} power, against an uncorrected rise of
{{GINIUNC}} per year.

\section{What the snapshot actually contains}
\label{si:provenance}

The provenance audit counts identifiers, but the two subsets that matter to a user of the
snapshot are the ones that carry readings and the ones the census lacks. Neither is a random
sample of the catalogue. The snapshot stores no theme field, so \texttt{broker\_name} is used
as the publisher-side proxy: it names the feed an instrument is ingested from, which is what
the archive's own theme directories are built from.

\begin{table}[H]
\centering
\caption{The identifiers carrying readings, by ingestion feed. The catalogue spans
{{NBROKERS}} feeds.}
\label{si:rbbroker}
\small
\begin{tabular}{lrr}
\toprule
Feed (broker) & Identifiers & Share of the {{RB}} with readings \\
\midrule
{{RBBROKER}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{Feeds contributing identifiers the census lacks, against the same feeds' share of the
matched set. Shares within each column are rounded to one decimal and need not sum to 100.}
\label{si:snapbroker}
\small
\begin{tabular}{lrrrr}
\toprule
 & \multicolumn{2}{c}{Snapshot-only ({{SNAPONLY}})} & \multicolumn{2}{c}{Matched ({{MATCH}})} \\
\cmidrule(lr){2-3}\cmidrule(lr){4-5}
Feed (broker) & $n$ & \% & $n$ & \% \\
\midrule
{{SNAPBROKER}}
\bottomrule
\end{tabular}
\end{table}

Two things follow. The reading-bearing subset is thematically narrow: it is dominated by air
quality and the LoRa network, and its readings are the air-quality and weather variables rather
than the vehicles, people counters or travel data that make up most of the catalogue, so an
execution target built on it exercises one corner of the platform. And the snapshot-only subset
is concentrated in building instrumentation, which is the opposite direction from the omission
contrast in Section~\ref{si:snapshot}: there the snapshot is short of vehicle counters, here it
is long on building sensors. Both are descriptions of a frozen artefact, not findings about the
observatory, and neither can be tested against a base rate outside this platform.

An implementation note, because it is a silent failure mode and not a diagnostic
message. The readings table joins to
the sensor table on the sensor \emph{name}, not on the numeric \texttt{raw\_id}, while the
census is keyed on \texttt{raw\_id}. Joining the readings table on \texttt{raw\_id} yields an
empty intersection ({{WRONGJOIN}} identifiers) and makes it look as though none of the
reading-bearing identifiers are in the census; the correct join gives {{RB}}, of which
{{RBINCENSUS}} are present.

\section{Core-definition sensitivity}
\label{si:coredef}

The core panel of the frame table uses a symmetric 5--95\% rectangle---percentile trims on $|x|$
and $|y|$ about the projection origin, not an interquartile box---which is an arbitrary
support. Table~\ref{si:core} sweeps it over five trims and adds four non-rectangular cores, so
the check is not confined to one family of supports. Every row declines and every row is
significant, so the core panel reports the network rather than the percentile.

\begin{table}[H]
\centering
\caption{Clark--Evans $R$ trend on nine core definitions, deduplicated locations, each with its
own support as the density denominator.}
\label{si:core}
\small
\begin{tabular}{lrrrr}
\toprule
Core & $R_{2013}$ & $R_{2026}$ & Slope/yr & OLS $p$ \\
\midrule
{{COREBODY}}
\bottomrule
\end{tabular}
\end{table}

\section{Grid-origin sensitivity for the concentration index}
\label{si:origin}

The concentration index is computed on a grid fixed in geographic space, so its origin is a
choice. Table~\ref{si:origin} shifts it over a $5\times5$ lattice of sub-cell positions at the
headline resolution and at a finer one. Every origin shows a rise, so the sign of the uncorrected
trend is not an artefact of where the grid starts; the magnitude varies by about 40\% at the
coarser resolution and by about 90\% at the finer one, which is why the text quotes the index
only with its partition named.

The same script re-checks Equation~(1) of the main text against the textbook form of the Gini
coefficient over \num{2000} random count vectors. The maximum absolute difference is
{{EQDIFF}}, so the printed formula and the code agree to machine precision.

\begin{table}[H]
\centering
\caption{Concentration-index trend over \num{25} grid origins, at two resolutions.}
\label{si:origintab}
\small
\begin{tabular}{lrrrr}
\toprule
Cells per side & Slope range & Mean & SD & All origins rise \\
\midrule
{{ORIGINBODY}}
\bottomrule
\end{tabular}
\end{table}

\section{Independent cross-check against \textsf{spatstat}}
\label{si:crosscheck}

The multiscale curve is computed with our own code. Table~\ref{si:xck} compares it with
\textsf{spatstat} 3.8.3 under R 4.6.1, on the same points with the same polygonal window and
\textsf{spatstat}'s own border correction. The two agree to a median of {{XCKMED}} per cent,
with the largest disagreement ({{XCKMAX}} per cent) at \SI{2}{\kilo\meter}, where the eroded
window retains the fewest pairs.

One convention difference is worth recording so that a reader comparing the two implementations
does not mistake it for a disagreement: \textsf{spatstat}'s \texttt{Lest} column named
\texttt{border} holds $\sqrt{K/\pi}$, whereas this paper's $L$ is $\sqrt{K/\pi} - r$. The two
therefore differ by exactly $r$ by construction, and the comparison here adds $r$ back so that
like is compared with like.

\begin{table}[H]
\centering
\caption{Manuscript estimator against \textsf{spatstat} \texttt{Lest} (border correction),
deduplicated locations, by scale. Absolute relative difference over the fourteen years.}
\label{si:xck}
\small
\begin{tabular}{lrr}
\toprule
Scale (m) & Median diff (\%) & Max diff (\%) \\
\midrule
{{XCKBODY}}
\bottomrule
\end{tabular}
\end{table}

\section{Thinning invariance: do the two indices measure the same thing?}
\label{si:thinning}

$K$ and $L$ are invariant under independent random thinning of a fixed pattern; the
Clark--Evans index is not written that way. Table~\ref{si:thin} gives each year's observed $R$
against the $R$ of a size-matched random draw from the pooled set of {{POOLED}} distinct
locations, which is the value each year's \emph{size alone} predicts for this network's
structure. A negative excess means the year is \emph{more} clustered than its size predicts,
because $R$ falls as clustering rises.

The 2013 network is indistinguishable from its size-matched draw; the 2026 network is more
clustered than its own size predicts by {{ZD26}} standard deviations. On a fixed clustered
pattern that is never moved, $R$ itself changes by only {{MECH}} per cent across a
sixteen-fold change in $n$, so the mechanism in which a falling $R$ is mechanical is
regime-dependent rather than automatic, and it has to be settled on the data.

The two references above disagree, and the disagreement is the subject of
Section~\ref{si:neardupsect}: thinning the 2026 network to $n = 39$ takes $R$ from 0.202 to 0.387, so
size alone reproduces the whole decline, whereas the pooled reference is nearly flat in $n$
(0.449 to 0.436). The near-duplicate test shows that the decline is substantially a
co-located-registration effect, which thinning and pooling absorb but the published
exact-coordinate deduplication does not.

\begin{table}[H]
\centering
\caption{Observed $R$ against the 2026 network thinned to each year's size. The $n = 561$ row is zero by construction.}
\label{si:thin}
\small
\begin{tabular}{lrrrr}
\toprule
Year & $n$ & $R$ observed & $R$ from thinned 2026 & Excess \\
\midrule
{{THINBODY}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{Observed $R$ against a size-matched random draw from the pooled structure, 400 draws per year. Negative $z$ means more clustered than the reference.}
\label{si:pooled}
\small
\begin{tabular}{lrrrrr}
\toprule
Year & $n$ & $R$ observed & $R$ from the pool & SD & $z$ \\
\midrule
{{POOLEDBODY}}
\bottomrule
\end{tabular}
\end{table}

\section{Near-duplicate registrations: the headline decline is tolerance-dependent}
\label{si:neardupsect}

The exact-coordinate deduplication used throughout the paper collapses only identifiers at the
\emph{same} coordinate. Two registrations a few metres apart survive it as two ``locations''.
Table~\ref{si:ndtable} reclusters every year's identifiers by single-linkage at radius $r$,
keeping one identifier per cluster, and recomputes the whole fixed-hull series. The
exact-coordinate row reproduces the published series, which is the control on the method.

The decline is not robust to the tolerance. At \SI{25}{\meter} the fall is {{NDFALL25}} and
the fitted slope is
{{NDSLOPE25}} per year ($p = {{NDP25}}$), against {{NDFALL0}} and $p = {{NDP0}}$ on the
published deduplication. Table~\ref{si:ndsweep} sweeps the radius from \SI{1}{\meter} to
\SI{50}{\meter} and shows the fall to be monotone with no plateau, reversing sign by
\SI{50}{\meter}; the radius is therefore a stated choice and not a threshold the data identify.
The merged identifiers are concentrated in the recent years:
the \SI{25}{\meter} merge removes {{NDMERGE26}} of 2026's {{NDN26}} identifiers, 145 of which
the exact-coordinate deduplication had already removed, against
{{NDMERGE13}} of 2013's {{NDN13}}. They are co-located instruments at one installation rather
than dispersed events, so at large $n$ they depress the nearest-neighbour mean, and thinning or
pooling breaks them up. That is the reconciliation of the two size-matched references of
Section~\ref{si:thinning}, which disagree because the pool has already absorbed the pairs and
the thinned reference has broken them.

\begin{table}[H]
\centering
\caption{The merge tolerance swept from \SI{1}{\meter} to \SI{50}{\meter}, single-linkage with one identifier kept per cluster. The fall has no plateau, and it reverses sign by \SI{50}{\meter}.}
\label{si:ndsweep}
\small
\begin{tabular}{lrrrr}
\toprule
Merge radius & 2013 $R$ & 2026 $R$ & Fall & OLS $p$ \\
\midrule
\SI{1}{\meter} & 0.367 & 0.202 & 44.9\% & 0.037 \\
\SI{2}{\meter} & 0.367 & 0.203 & 44.7\% & 0.038 \\
\SI{5}{\meter} & 0.367 & 0.211 & 42.5\% & 0.053 \\
\SI{10}{\meter} & 0.367 & 0.242 & 34.1\% & 0.120 \\
\SI{15}{\meter} & 0.367 & 0.290 & 21.1\% & 0.359 \\
\SI{25}{\meter} & 0.367 & 0.351 & 4.3\% & 0.742 \\
\SI{50}{\meter} & 0.367 & 0.392 & $-6.8$\% & 0.320 \\
\bottomrule
\end{tabular}
\end{table}

The same result is reported in the main text's tolerance figure, which also gives the
nearest-neighbour distance distribution. That distribution is smooth: the largest gap below
\SI{200}{\meter} is \SI{35}{\meter} in 2014 and \SIrange{6}{26}{\meter} in every other year, so
no trough separates a co-located population from distinct installations and no radius is
singled out by the data. The merge is also not specific to single-linkage: complete-linkage at
the same radius gives 4.7\% ($p = 0.77$) and a centroid representative gives 4.3\%, while the
largest cluster single-linkage forms at \SI{25}{\meter} has a diameter of \SI{74}{\meter} against
a median of \SI{12}{\meter}, so chaining is bounded. Snapping to a \SI{25}{\meter} grid instead
gives 31.1\% ($p = 0.15$), which shows the result is not entirely independent of the merge rule.

\begin{table}[H]
\centering
\caption{The fixed-hull location series under tolerance deduplication. Clusters are formed by
single-linkage at radius $r$ and one identifier is kept per cluster. The exact-coordinate row is
the published series.}
\label{si:ndtable}
\small
\begin{tabular}{lrrrrrr}
\toprule
Deduplication & 2013 $R$ & 2026 $R$ & Fall & Slope/yr & OLS $p$ & 2026 pooled $z$ \\
\midrule
{{NDBODY}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{Identifiers merged by tolerance deduplication, by year. The tight clusters accumulate
over the record.}
\label{si:ndmerge}
\small
\begin{tabular}{lrrrrr}
\toprule
Year & Identifiers & Sites at \SI{5}{\meter} & Sites at \SI{10}{\meter} & Sites at \SI{25}{\meter} & Removed at \SI{25}{\meter} \\
\midrule
{{NDMERGE}}
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{The pooled size-matched reference recomputed on the \SI{25}{\meter} deduplication, so
Table~\ref{si:pooled} can be re-read under the wider tolerance. The separation shrinks but does
not vanish.}
\label{si:ndpooled}
\small
\begin{tabular}{lrrrrr}
\toprule
Year & $n$ & $R$ observed & $R$ from pool & SD of draws & $z$ \\
\midrule
{{NDPOOLEDBODY}}
\bottomrule
\end{tabular}
\end{table}

\section{Multiplicity, the random seed and the code}
\label{si:mult}
The paper reports about {{NCOMP}} fitted comparisons when the level series are counted by frame,
unit and year, the concentration index by resolution and year, the rarefaction anchors, the
interval procedures and the bandwidth sweep. They are not corrected as one family, because many
are descriptive readings of one series under different frames rather than independent
hypotheses, but the size of the search is stated.

The one family that \emph{is} corrected as a family is the per-year clustering test, because
those tests are the same question asked repeatedly. Table~\ref{si:bh} gives each year pair its
raw one-sided Monte Carlo $p$-value and the Benjamini--Hochberg adjusted value across the
thirteen pairs. The correction is applied to thirteen tests rather than fourteen years, because
each pair is compared only against the pooled positions of that pair; it is approximate, because
successive pairs share a year. {{BHPAR}}

\begin{table}[H]
\centering
\caption{Per-year clustering test against the pooled-subset null, with the Benjamini--Hochberg step-up. The $p$-value is one-sided: the share of pooled random subsets with a median new-to-new distance no greater than the observed one.}
\label{si:bh}
\small
\begin{tabular}{lrrrrl}
\toprule
Year & $n$ new & Obs. (m) & Pooled 95\% (m) & $p$ & $p_{BH}$ \\
\midrule
{{BHBODY}}
\bottomrule
\end{tabular}
\end{table}

All draws use one fixed seed (\texttt{20261003}). The seed enters the rarefied series through
the subsampling draws, and Table~\ref{si:seed} bounds its effect.

\begin{table}[H]
\centering
\caption{Random-seed sensitivity of the rarefied clustering slope on the fixed hull.}
\label{si:seed}
\small
\begin{tabular}{lrr}
\toprule
Seed & Slope per year & Interval contains zero \\
\midrule
20261003 & $+0.0003$ & yes \\
20261004 & $+0.0003$ & yes \\
20261005 & $+0.0005$ & yes \\
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{Analysis scripts and the files they produce.}
\label{si:scripts}
\small
\begin{tabular}{p{5.2cm}p{7.4cm}}
\toprule
Script & Produces \\
\midrule
\texttt{build\_archive\_index.py} & \texttt{uo\_archive\_index.json}, the per-year census \\
\texttt{analysis\_common.py} & core analyses, reference frames, uncertainty \\
\texttt{analysis\_multiscale.py} & multiscale estimator and its controls \\
\texttt{analysis\_trendtests.py} & correctly sized trend tests, infill count \\
\texttt{analysis\_inhomogeneous.py} & multiscale vs the inhomogeneous null \\
\texttt{analysis\_snapshot.py} & the snapshot audit, conditioned \\
\texttt{analysis\_edge.py} & edge correction, endpoint, themes, gap-filled \\
\texttt{analysis\_envelope.py} & CSR envelope, leave-one-out intensity \\
\texttt{analysis\_exclusions.py} & Gini MDE, exclusion sweeps \\
\texttt{analysis\_snapdupes.py} & snapshot-only identifiers, by location \\
\texttt{analysis\_feeds.py} & snapshot composition by ingestion feed \\
\texttt{analysis\_coredefs.py} & core-definition (MAUP) sweep \\
\texttt{analysis\_gridorigin.py} & grid-origin sweep, equation check \\
\texttt{analysis\_donnelly.py} & Donnelly edge correction \\
\texttt{analysis\_thinning.py} & thinning invariance, size-matched test \\
\texttt{analysis\_neardup.py} & tolerance deduplication, the near-duplicate test \\
\texttt{crosscheck\_spatstat.R} & independent comparison against \textsf{spatstat} \\
\texttt{crosscheck\_spatstat.py} & compares the two estimators \\
\texttt{crosscheck\_donnelly.R} & Clark--Evans against spatstat's cdf correction \\
\texttt{make\_study\_area\_figure.py} & Figure~1, the study area \\
\texttt{make\_supplement.py} & this document \\
\texttt{verify\_ripley\_sign.py} & known-answer control for the multiscale estimator \\
\bottomrule
\end{tabular}
\end{table}

% THE SUPPLEMENT'S OWN REFERENCE LIST. This document carries three citations and is published
% as its own file, so a reader who downloads only this cannot be sent to the main text for
% them. It shares references.bib with the manuscript, so the two cannot disagree about a
% reference.
\section*{References}
\bibliography{references}

\end{document}
"""

    # ---- per-year-pair clustering test and its BH step-up (results_core.json) ----
    core = json.loads((HERE / "results_core.json").read_text())
    bh = core.get("batch_pooled", [])
    t_bh = "\n".join(
        r"%d & %d & %.0f & [%.0f, %.0f] & %s & %s \\"
        % (r["year"], r["n_new"], r["obs"], r["pooled_lo"], r["pooled_hi"],
           f3(r["p_one_sided"]), f3(r["p_adj_bh"]))
        for r in bh)
    surv = core.get("bh_pooled_survivors", [])
    nbh = core.get("bh_pooled_n_tests", len(bh))
    bhp = ("%d of the %d year pairs survive at a \\SI{5}{\\percent} false-discovery rate: %s. "
           "The three that do not --- %s --- are the same years whose observed distance falls "
           "inside the pooled-subset interval at the single-test level, so the correction removes "
           "exactly the years the uncorrected test could not separate."
           % (len(surv), nbh, ", ".join(str(y) for y in surv),
              ", ".join(str(r["year"]) for r in bh if not r.get("survives_bh"))))

    text = render(
        DOC,
        SZ0=pct(r13b["size_sim"]["rho_0"]["nw_reject"]),
        SZ3=pct(r13b["size_sim"]["rho_0.15"]["nw_reject"]),
        TREND=t_trend, SIZE=t_size, ANCHOR=t_anchor,
        RARER=t_rare_r,
        EDGE=t_edge, EDGETREND=t_edge_trend,
        EP=t_ep, THEME=t_theme, GAPL=t_gapL,
        NMIN=r8["R8.3_scale"]["nmin"],
        HULLKM="%.0f" % r8["R8.3_scale"]["A_hull_km2"],
        ENN="%.0f" % r8["R8.3_scale"]["expected_nn_m"],
        LOCMIN=gini["nmin"],
        RSCOLS="r" * len(rs),
        RSHEAD=" & ".join("%d m" % r for r in rs),
        LCTRL=t_lctrl, LNULL=t_lnull, LSHAPE=t_lshape,
        GINIGRID=t_gini_grid,
        CDFSERIES=t_cdfseries,
        INFILLRATIOS=t_infill_ratios, INFILLRL=t_infill_rl,
        CREATED=r13d["snapshot_creation_utc"][:10],
        WINLO=r13d["readings_window"][0][:10],
        WINHI=r13d["readings_window"][1][:10],
        SNAPID=r13d["snapshot_ids"], SNAPREAD=r13d["snapshot_ids_with_readings"],
        CENSUS=r13d["census_ids"], MATCHED=r13d["matched"],
        ONLYSNAP=r13d["only_snapshot"], ONLYCENSUS=r13d["only_census"],
        COVGEO="%.1f\\%%" % r13d["coverage_of_census"],
        ACT26=r13d["n_active_2026_census"],
        ACT26IN=r13d["n_active_2026_in_snapshot"],
        ACT26OUT=r13d["n_active_2026_omitted"],
        COV26="%.1f\\%%" % r13d["coverage_active_2026"],
        OMVEH=veh["table"][0][0], OMOTH=veh["table"][0][1],
        OMSHARE=pct(veh["omitted_2026cond"]),
        INVEH=veh["table"][1][0], INOTH=veh["table"][1][1],
        INSHARE=pct(veh["matched_2026cond"]),
        OR="%.2f" % veh["odds_ratio"], FISHER="%.3g" % veh["fisher_p"],
        NRUN=r15["nrun"],
        ENVBODY=t_env,
        ENVBIAS=t_envbias,
        BIASFRAC=t_biasfrac,
        LOOBODY=t_loo,
        SNAPDUPN=r15c["n_snapshot_only"],        SNAPDUPBODY=t_snapdup,
        EXCLBODY=t_excl,
        INFLEXCL=t_inflexcl,
        GINIMDE="%.4f" % r15b["gini_mde"]["mde80"],
        GINIUNC="%.4f" % r15b["gini_mde"]["uncorrected_slope"],
        NBROKERS=r16["representativeness"]["n_brokers_in_snapshot"],
        RB=r16["reading_bearing"]["n"],
        RBINCENSUS=r16["reading_bearing"]["in_census"],
        WRONGJOIN=r16["reading_bearing"]["matched_via_raw_id_wrong_join"],
        RBBROKER=t_rbbroker,
        SNAPBROKER=t_snapbroker,
        SNAPONLY=r16["snapshot_only"],
        MATCH=r16["matched"],
        COREBODY=t_core,
        ORIGINBODY=t_origin,
        XCKBODY=t_xck,
        XCKMED="%.2g" % __import__("statistics").median(
            [abs(r["pct_diff"]) for r in xck["rows"]]),
        XCKMAX="%.2f" % xck["worst_pct"],
        THINBODY=t_thin,
        POOLED=1567,
        POOLEDBODY=t_pooled,
        MECH="%.0f" % (100 * abs(
            r17["mechanism"][-1]["R"] - r17["mechanism"][0]["R"])
            / r17["mechanism"][0]["R"]),
        ZD26="%.1f" % abs([r for r in r17["vs_pooled"] if r["year"] == 2026][0]["z"]),
        NDBODY=t_nd,
        NDMERGE=t_ndmerge,
        NDPOOLEDBODY=t_ndpooled,
        NDFALL0="%.1f\\%%" % nd0["fall_pct"],
        NDFALL25="%.1f\\%%" % nd25["fall_pct"],
        NDSLOPE25="$%+.4f$" % nd25["slope"],
        NDP0="%.3f" % nd0["ols_p"],
        NDP25="%.2f" % nd25["ols_p"],
        NDMERGE26=nd25["rows"][-1]["merged"],
        NDMERGE13=nd25["rows"][0]["merged"],
        NDN26=nd25["rows"][-1]["n_raw"],
        NDN13=nd25["rows"][0]["n_raw"],
        EQDIFF="$%.1f\\times10^{-16}$" % (r16d["equation1_max_abs_diff"] * 1e16),
        NCOMP=182, BHBODY=t_bh, BHPAR=bhp,
    )
    (HERE / "main_si.tex").write_text(text)
    print("wrote main_si.tex (%d bytes)" % (HERE / "main_si.tex").stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
