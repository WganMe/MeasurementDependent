#!/usr/bin/env Rscript
# Independent cross-check of the multiscale estimator against spatstat.
#
# The manuscript computes L(r) with its own border-corrected estimator and says, in
# three separate places, that spatstat's Lest was not run because R was unavailable.
# R is now installed (4.6.1) together with spatstat.explore (3.8.3), so the check
# the paper reports can be done.
#
# spatstat uses a DIFFERENT window object (owin, polygonal) and its own border
# correction, so agreement here is evidence that the manuscript's estimator and
# window are not a local misreading.
#
# Input : /tmp/si_crosscheck/points_<year>.csv, one row per deduplicated location,
#         columns x,y in metres (the manuscript's projection), plus hull.csv.
# Output: /tmp/si_crosscheck/spatstat_L.csv

suppressPackageStartupMessages({
  library(spatstat.geom)
  library(spatstat.explore)
})

dir <- "/tmp/si_crosscheck"
rs <- c(0, 100, 250, 500, 750, 1000, 1500, 2000)   # spatstat requires r to start at 0

hull <- read.csv(file.path(dir, "hull.csv"))
W <- owin(poly = list(x = hull$x, y = hull$y))

files <- sort(list.files(dir, pattern = "^points_[0-9]+\\.csv$", full.names = TRUE))
cat(sprintf("hull window: area %.0f km2, %d vertices\n",
            area(W) / 1e6, nrow(hull)))
cat(sprintf("cross-checking %d years against spatstat Lest (border correction)\n\n",
            length(files)))

out <- list()
for (f in files) {
  yr <- as.integer(sub(".*points_([0-9]+)\\.csv", "\\1", f))
  df <- read.csv(f)
  X <- ppp(df$x, df$y, window = W)
  # Lest gives L(r) - r in spatstat's convention; Kest gives K(r).
  L <- Lest(X, r = rs, correction = "border", ratio = FALSE)
  # convert spatstat's L-r back to the manuscript's L = sqrt(K/pi)
  K <- Kest(X, r = rs, correction = "border")
  Lm <- sqrt(pmax(K$border, 0) / pi)          # this is the manuscript's L
  for (i in seq_along(rs)) {
    out[[length(out) + 1]] <- data.frame(
      year = yr, r = rs[i], n = X$n,
      spatstat_L = Lm[i],
      spatstat_Lmr = L$border[i],
      spatstat_K = K$border[i]
    )
  }
  cat(sprintf("  %d  n=%-4d  L(1000 m) = %.1f m   K(1000 m) = %.3e\n",
              yr, X$n, Lm[which(rs == 1000)], K$border[which(rs == 1000)]))
}

res <- do.call(rbind, out)
write.csv(res, file.path(dir, "spatstat_L.csv"), row.names = FALSE)
cat(sprintf("\nwrote %s (%d rows)\n", file.path(dir, "spatstat_L.csv"), nrow(res)))
