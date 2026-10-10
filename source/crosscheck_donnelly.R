#!/usr/bin/env Rscript
# Independent cross-check of the Clark-Evans index against spatstat, on the same
# points and the same polygonal window the manuscript uses.
#
# WHY: the manuscript reports the raw Clark-Evans index as the headline and
# Donnelly's edge-corrected value as a sensitivity. It states that Donnelly's
# correction "uses the window's area and perimeter ... a convex hull has both, so
# the correction does apply here".
#
# spatstat disagrees, and this script records the disagreement rather than
# resolving it by assertion: clarkevans(X, correction = "donnelly") raises
#     "Donnelly correction only available for rectangular windows"
# The reference implementation treats the correction as rectangle-only, even
# though the published formula is written in terms of area and perimeter.
# Donnelly's coefficients were estimated by simulation on rectangles, and
# applying them to a polygon of very different shape is exactly what is at issue.
#
# The correction that IS available for a polygon is "cdf", which compares the
# observed mean nearest-neighbour distance with the mean nearest-neighbour
# distance of random points drawn in the same window. That needs no rectangular
# assumption, so it is the general-region correction to report beside the raw index.
#
# Input : /tmp/si_crosscheck/points_<year>.csv (x,y metres) and hull.csv
# Output: /tmp/si_crosscheck/donnelly.csv and a printed table
#
# Usage: Rscript crosscheck_donnelly.R

suppressPackageStartupMessages({
  library(spatstat.geom)
  library(spatstat.explore)
})

dir <- "/tmp/si_crosscheck"
hull <- read.csv(file.path(dir, "hull.csv"))
W <- owin(poly = list(x = hull$x, y = hull$y))
A <- area.owin(W)
per <- perimeter(W)
cat(sprintf("window: convex hull, area = %.1f m^2 (%.1f km^2), perimeter = %.0f m\n",
            A, A / 1e6, per))

# --- record spatstat's own position on Donnelly for a polygon ----------------
donnelly_ok <- TRUE
msg <- tryCatch({
  invisible(clarkevans(ppp(c(0, 1), c(0, 1), window = W), correction = "donnelly"))
  NA_character_
}, warning = function(w) conditionMessage(w), error = function(e) conditionMessage(e))
if (!is.na(msg)) {
  donnelly_ok <- FALSE
  cat(sprintf("spatstat refuses Donnelly on this window: \"%s\"\n", msg))
} else {
  cat("spatstat accepted Donnelly on this window.\n")
}

years <- 2013:2026
rows <- list()
for (y in years) {
  f <- file.path(dir, sprintf("points_%d.csv", y))
  if (!file.exists(f)) next
  d <- read.csv(f)
  X <- ppp(d$x, d$y, window = W, check = FALSE)
  n <- npoints(X)

  raw <- as.numeric(clarkevans(X, correction = "none"))
  cdf <- as.numeric(clarkevans(X, correction = "cdf"))
  don <- if (donnelly_ok) as.numeric(clarkevans(X, correction = "donnelly")) else NA_real_

  rows[[length(rows) + 1]] <- data.frame(
    year = y, n = n, dbar_m = mean(nndist(X)),
    R_raw = raw, R_cdf = cdf, R_donnelly = don
  )
}

tab <- do.call(rbind, rows)
tab$cdf_vs_raw_pct <- 100 * (tab$R_cdf - tab$R_raw) / tab$R_raw

print(tab, row.names = FALSE, digits = 4)
write.csv(tab, file.path(dir, "donnelly.csv"), row.names = FALSE)

fit <- function(v) coef(lm(v ~ years))[2]
p_of <- function(v) summary(lm(v ~ years))$coefficients[2, 4]
cat(sprintf("\nslope on year  raw %+.5f (p = %.4f)\n", fit(tab$R_raw), p_of(tab$R_raw)))
cat(sprintf("slope on year  cdf %+.5f (p = %.4f)\n", fit(tab$R_cdf), p_of(tab$R_cdf)))
cat(sprintf("\n2013 -> 2026 fall: raw %.1f%%, cdf %.1f%%\n",
            100 * (tab$R_raw[1] - tab$R_raw[nrow(tab)]) / tab$R_raw[1],
            100 * (tab$R_cdf[1] - tab$R_cdf[nrow(tab)]) / tab$R_cdf[1]))

# --- CSR control: does the cdf correction return 1 on randomness? -----------
set.seed(20261003)
cat("\nCSR control in the same hull (200 draws at n = 500):\n")
raws <- numeric(200); cdfs <- numeric(200)
for (i in 1:200) {
  P <- runifpoint(500, win = W)
  raws[i] <- as.numeric(clarkevans(P, correction = "none"))
  cdfs[i] <- as.numeric(clarkevans(P, correction = "cdf"))
}
cat(sprintf("  raw  %.4f (sd %.4f)\n", mean(raws), sd(raws)))
cat(sprintf("  cdf  %.4f (sd %.4f)\n", mean(cdfs), sd(cdfs)))

# --- our own area+perimeter Donnelly form, on CSR in the hull ---------------
# Donnelly (1978): E[d] ~ 1/(2 sqrt(N/A)) + (0.0514 + 0.041/sqrt(N)) (P/N)
# The coefficients come from a rectangular simulation study, which is the point
# at issue: this prints what the form does on a polygon of this shape.
cat("\nOur area+perimeter Donnelly form applied to the hull (50 draws each):\n")
for (n in c(50, 100, 200, 500, 1000, 2000)) {
  v <- numeric(50)
  for (i in 1:50) {
    P <- runifpoint(n, win = W)
    ex <- 1 / (2 * sqrt(n / A)) + (0.0514 + 0.041 / sqrt(n)) * (per / n)
    v[i] <- mean(nndist(P)) / ex
  }
  cat(sprintf("  n = %4d   mean R = %.3f  (sd %.3f)\n", n, mean(v), sd(v)))
}
