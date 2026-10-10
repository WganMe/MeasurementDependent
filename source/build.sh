#!/usr/bin/env bash
# Reliable manuscript build: clean 4-pass pdflatex/bibtex, then VERIFY the PDF parses.
# A killed/interrupted pdflatex leaves a truncated main.pdf that all readers reject
# ("Command token too long"); latexmk can still report success, so we check pdfinfo.
set -euo pipefail
cd "$(dirname "$0")"

rm -f main.pdf main.aux main.bbl main.blg main.out main.log main.synctex.gz

# TeX output is captured rather than sent to /dev/null. A silent pdflatex means a
# failed build reports only "exit code 1", with no indication of the cause -- which
# is exactly how a CI failure becomes undiagnosable. On failure the tail of the log
# is printed here, so the reason is visible without downloading artefacts.
run_tex() {
  if ! pdflatex -interaction=nonstopmode -halt-on-error main.tex >"$1" 2>&1; then
    echo "BUILD FAILED: pdflatex (see below)" >&2
    echo "----- last 40 lines of TeX output -----" >&2
    tail -40 "$1" >&2
    echo "----- errors -----" >&2
    grep -E '^! ' "$1" >&2 || true
    exit 1
  fi
}

run_tex /tmp/tex_pass1.log
bibtex main >/dev/null
run_tex /tmp/tex_pass2.log
run_tex /tmp/tex_pass3.log

pages=$(pdfinfo main.pdf 2>/dev/null | awk '/^Pages:/{print $2}')
if [ -z "${pages:-}" ]; then
  echo "BUILD FAILED: main.pdf is not parseable (likely truncated by an interrupted run)" >&2
  exit 1
fi

undef=$(grep -cE 'Reference .* undefined|Citation .* undefined' main.log || true)
over=$(grep -c 'Overfull' main.log || true)
errs=$(grep -cE '^! ' main.log || true)
echo "OK: $pages pages; undefined=$undef overfull=$over errors=$errs"

# Leave the tree clean. The check above is the only reason main.log is needed,
# so the intermediates are removed once it has run. Set KEEP=1 to inspect them.
if [ "${KEEP:-0}" != "1" ]; then
  rm -f main.aux main.bbl main.blg main.out main.log main.fls main.fdb_latexmk \
        main.synctex.gz main.toc
fi
