#!/usr/bin/env bash
# Build the whole PeerJ submission from source.
#
# WHY A SCRIPT. The order matters and was got wrong: BibTeX must run AFTER a first pass
# that writes the .aux, and LaTeX needs enough passes afterwards to resolve every label.
# Running `pdflatex` twice produced "No file peerj-main.bbl" on the first pass and left the
# bibliography unresolved, and two passes leave some of the 39 cross-reference labels
# undefined, which silently shortened the paper to 19 pages.
#
# The recipe, verified:
#   pass 1  -> writes .aux (citations requested)
#   bibtex  -> reads .aux, writes .bbl; the ONLY pass that reads the .bbl is a later pdflatex
#   pass 2  -> reads .bbl, sets citation numbers and \bibcite entries
#   pass 3+ -> settles page numbers and cross-references
#
# Usage:  ./build.sh          (from the repository root)
set -euo pipefail

export PATH=/usr/local/texlive/2026/bin/x86_64-linux:$PATH
cd "$(dirname "$0")"

# 1. regenerate the PeerJ documents from the neutral source
(cd source && python3 convert_to_peerj.py)

# 2. typeset: first pass, BibTeX, then enough passes to resolve everything
#
# BibTeX is run only when the document actually cites something. The supplement is
# tables-only and carries no \citation commands, and BibTeX treats that as an error
# ("I found no \citation commands") and exits 2 -- which, under `set -e`, aborted the whole
# build after the supplement had already been typeset. The `|| true` is therefore not
# sloppiness: a citation-free document is the expected state for the supplement, not a
# failure. The real failure signal is the undefined-citation count reported in step 3.
for d in peerj-main peerj-si; do
    pdflatex -interaction=nonstopmode "$d.tex" >/dev/null
    if grep -q '\\citation{' "$d.aux"; then
        bibtex "$d" >/dev/null || true
    else
        echo "  $d: no citations, skipping BibTeX"
    fi
    for _ in 1 2 3; do pdflatex -interaction=nonstopmode "$d.tex" >/dev/null; done
done
for _ in 1 2; do pdflatex -interaction=nonstopmode peerj-cover.tex >/dev/null; done

# 3. report, and fail loudly rather than shipping a half-built document
status=0
for d in peerj-main peerj-si peerj-cover; do
    errors=$(grep -c '^!' "$d.log" || true)
    undef=$(grep -c 'Citation.*undefined' "$d.log" || true)
    overfull=$(grep -c Overfull "$d.log" || true)
    pages=$(grep -oE '\([0-9]+ pages?' "$d.log" | tail -1 | grep -oE '[0-9]+' || echo "?")
    printf '%-14s errors=%s undefined-citations=%s overfull=%s pages=%s\n' \
        "$d" "$errors" "$undef" "$overfull" "$pages"
    [ "$errors" = "0" ] && [ "$undef" = "0" ] || status=1
done
[ "$status" = "0" ] || { echo "BUILD FAILED: see the .log files above" >&2; exit 1; }

# 4. bundle
python3 make_peerj_bundle.py
