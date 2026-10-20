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

# 1b. the portal's plain-text Title / Short Title / Abstract fields, extracted from the PDF
python3 source/make_portal_fields.py

# 2. typeset: first pass, BibTeX, then enough passes to resolve everything
#
# BibTeX is run only when the document actually cites something. The supplement USED to be
# tables-only with no \citation commands, and BibTeX treats that as an error ("I found no
# \citation commands") and exits 2 -- which, under `set -e`, aborted the whole build. It now
# cites Ripley, Donnelly and spatstat, so it has a bibliography of its own and BibTeX is
# expected to run; the guard stays because a future edit could remove the citations again.
# The real failure signal is the undefined-citation count reported in step 3.
for d in peerj-main peerj-si; do
    # THE PASSES ARE PREFIXED WITH `|| true` AND THE LOG IS THE GATE. pdflatex
    # exits non-zero for ordinary, self-correcting conditions: on the FIRST pass
    # there is no .bbl yet, so natbib reports "Bibliography not compatible with
    # author-year citations" and exits 1 -- but BibTeX then writes the .bbl and
    # the NEXT pass reads it and typesets author-year citations correctly. Under
    # `set -e` that first exit aborted the whole build before BibTeX ever ran, so
    # `./build.sh` reported failure while the PREVIOUS PDF sat on disk looking
    # current. Measured: the build exited 1 with no `errors=` line at all, and the
    # committed PDF had 60 correct author-year citations -- i.e. the script was
    # broken, not the document.
    #
    # The real gate is the error count in the FINAL log, which step 3 still
    # applies. A pass that cannot succeed at all will leave `!` lines there.
    pdflatex -interaction=nonstopmode "$d.tex" >/dev/null || true
    if grep -q '\\citation{' "$d.aux"; then
        bibtex "$d" >/dev/null || true
    else
        echo "  $d: no citations, skipping BibTeX"
    fi
    for _ in 1 2 3; do pdflatex -interaction=nonstopmode "$d.tex" >/dev/null || true; done
done
# NO SEPARATE COVER BUILD. The Author Cover Page is part of peerj-main.tex now -- PeerJ's
# template says it "must be included in your main manuscript" -- so there is no third document
# to typeset. peerj-cover.tex is still generated as the source of that content.

# 3. report, and fail loudly rather than shipping a half-built document
status=0
for d in peerj-main peerj-si; do
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

# 4b. fail the local build on a sign-inverting glyph. PeerJ's production pipeline rewrites the
# ToUnicode maps of the CM math-symbol fonts, so a minus set from CMSY10 left their reviewing
# PDF as the digit "2" ("−99 m per year" published as "299"). `final_audit.py` guards this and
# the figure axis labels; run it here too so the defect cannot reach a commit that CI has not
# yet seen. It exits non-zero only for a sign-inverting glyph, not for the notation glyphs it
# reports.
python3 source/final_audit.py > /tmp/peerj-final-audit.txt || {
    echo "BUILD FAILED: final_audit.py rejected the documents; see /tmp/peerj-final-audit.txt" >&2
    tail -20 /tmp/peerj-final-audit.txt >&2
    exit 1
}

# 5. regenerate the portal fields, which now describe the BUILT archives.
# This generator runs at step 1b so the portal text exists before the documents are typeset,
# but its Title/Legend section reads file counts out of the bundle -- which by definition does
# not exist yet at step 1b. Running it a second time here means the counts are present rather
# than omitted. It is cheap and has no side effects on the documents.
python3 source/make_portal_fields.py >/dev/null
