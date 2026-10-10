#!/usr/bin/env python3
"""Final audit of the manuscript against the five stated requirements.

WHERE THE FILES ARE. This script reads the NEUTRAL source and the GENERATED documents, and
those live in different places. `main.tex` and `main_si.tex` are this directory (`source/`),
but the typeset output is written to the repository root as `peerj-main.*`, because the root
is the submission folder. The bibliography is shared, so it is read from the source copy.

The script used to look for `main.pdf`, `main.log`, `main.blg` and `main.bbl` beside itself,
which stopped existing when the generated documents moved one level up and were renamed. It
then crashed on the first read, so this whole audit had been silently dead -- including its
uncited-bibliography-entry report, which is the one output here that nothing else produces.
"""
import json
import pathlib
import re
import subprocess
import sys
from collections import Counter

PAPER = pathlib.Path(__file__).resolve().parent          # source/
ROOT = PAPER.parent                                      # the submission folder

TEX = (PAPER / "main.tex").read_text()
BIB = (PAPER / "references.bib").read_text()
BODY = TEX.split("\\begin{document}", 1)[1]

# The generated documents, under their PeerJ names, at the repository root.
PDF = ROOT / "peerj-main.pdf"
LOG = ROOT / "peerj-main.log"
BLG = ROOT / "peerj-main.blg"
BBL = ROOT / "peerj-main.bbl"

_missing = [p.name for p in (PDF, LOG, BLG, BBL) if not p.exists()]
if _missing:
    raise SystemExit(
        "REFUSING: the generated documents are missing from %s: %s\n"
        "Run ./build.sh at the repository root first." % (ROOT, ", ".join(_missing)))

print("=" * 68)
print(" FINAL AUDIT — five requirements, measured")
print("=" * 68)

# ---------- 1. published sources only ----------
print("\n[1] PUBLISHED SOURCES ONLY")
print("    preprint wording anywhere : %s"
      % ("none" if not re.search(
          r"arxiv|biorxiv|medrxiv|techrxiv|ssrn|preprint|research.?square",
          BIB, re.I) else "FOUND"))
print("    'posted-content' entries  : %d"
      % len(re.findall(r"10\.5194|10\.21203|10\.2139|10\.36227|10\.20944", BIB)))
n = len(re.findall(r"@\w+\{([^,]+),", BIB))
nodoi = []
for m in re.finditer(r"@(\w+)\{([^,]+),(.*?)\n\}", BIB, re.S):
    if not re.search(r"doi\s*=", m.group(3), re.I):
        nodoi.append((m.group(2), bool(re.search(r"(note|howpublished)\s*=", m.group(3), re.I))))
print("    total entries             : %d" % n)
print("    entries lacking a DOI     : %d" % len(nodoi))
for k, has in nodoi:
    print("        %-24s source field: %s" % (k, "yes" if has else "*** NONE ***"))

# ---------- 2. justification ----------
print("\n[2] TEXT JUSTIFICATION")
pre = TEX.split("\\begin{document}")[0]
print("    raggedright in preamble   : %d" % len(
    [l for l in pre.splitlines() if "ragged" in l.lower()]))
just = subprocess.run([sys.executable, str(PAPER / "check_justification.py")],
                      capture_output=True, text=True).stdout
m = re.search(r"flush to the right margin \d+ \((\d+)%\)", just)
v = re.search(r"VERDICT: (.+)", just)
print("    body lines flush to margin: %s" % (m.group(1) + "%" if m else "?"))
print("    verdict                   : %s" % (v.group(1) if v else "?"))
print("    (measured from glyph xMax via pdftotext -bbox; a character-count test")
print("     is wrong here because paragraph-final lines, captions and the")
print("     full-width title block all end short legitimately)")

# ---------- 3. abbreviations ----------
print("\n[3] SHORT TERMS DEFINED AT FIRST USE")
clean = re.sub(r"\$[^$]*\$", " ", BODY)
clean = re.sub(r"\\cite[a-zA-Z]*\{[^}]*\}", " ", clean)
clean = re.sub(r"\\SI\{[^}]*\}\{[^}]*\}", " ", clean)
for ab, full in [("CSV", "comma-separated-value"),
                 ("API", "application-programming interface"),
                 ("NUO", "Newcastle Urban Observatory"),
                 ("FDR", "false discovery rate"),
                 ("OLS", "ordinary least squares"),
                 ("CI", "confidence interval"),
                 ("AI", "artificial intelligence"),
                 ("IoT", "internet of things")]:
    used = len(re.findall(r"\b%s\b" % re.escape(ab), clean))
    defined = bool(re.search(r"\(%s\)" % re.escape(ab), clean))
    if not used:
        continue
    print("    %-5s used %-3d defined at first use: %s"
          % (ab, used, "yes" if defined else "NO"))

# ---------- 4. duplication ----------
print("\n[4] DUPLICATION")
t = re.sub(r"\\begin\{(table|figure)\*?\}.*?\\end\{\1\*?\}", " ", BODY, flags=re.S)
t = re.sub(r"%.*", "", t)
t = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", t)
t = re.sub(r"[{}$]", " ", t)
prose = " ".join(t.split())
words = re.findall(r"[a-z']+", prose.lower())
grams = Counter(tuple(words[i:i + 6]) for i in range(len(words) - 5))
rep = [(c, g) for g, c in grams.items()
       if c > 1 and sum(len(w) for w in g) > 18]
rep.sort(reverse=True)
print("    repeated 6-word phrases   : %d" % len(rep))
for c, g in rep[:6]:
    print("        x%d  %s" % (c, " ".join(g)))
sents = [" ".join(x.split()) for x in re.split(r"(?<=[.!?])\s+", prose)
         if len(x.split()) > 6]
dups = 0
for i, a in enumerate(sents):
    wa = set(re.findall(r"[a-z']+", a.lower()))
    for b in sents[i + 1:]:
        wb = set(re.findall(r"[a-z']+", b.lower()))
        if wa and wb and len(wa & wb) / min(len(wa), len(wb)) >= 0.70:
            dups += 1
print("    near-duplicate sentence pairs (>=70%%): %d" % dups)

# ---------- 5. AI tells ----------
print("\n[5] AI-STYLE TELLS")
for k, pat in [("em-dash ---", r"---"),
               ("'rather than'", r"rather than"),
               ("'not merely/only'", r"not (merely|only)"),
               ("'we state/decline/claim'", r"\bwe (state|decline|claim)\b"),
               ("'first,/second,' list", r"\b(first|second|third|finally),"),
               ("tricolon A, B, and C", r"\b\w+,\s+\w+,?\s+and\s+\w+"),
               ("'plays a crucial role'", r"plays a (crucial|key|vital) role"),
               ("'it is worth noting'", r"it is worth noting"),
               ("'in order to'", r"in order to")]:
    print("    %-28s %d" % (k, len(re.findall(pat, prose, re.I))))
S = [len(x.split()) for x in re.split(r"(?<=[.!?])\s+", prose) if x.strip()]
print("    prose words %d | sentences %d | mean %.1f | max %d | >45w %d"
      % (len(prose.split()), len(S), sum(S) / len(S), max(S),
         sum(1 for x in S if x > 45)))

# ---------- build ----------
print("\n[6] BUILD")
# peerj-main.log holds only the LAST pdflatex pass. Earlier passes legitimately warn
# that citations are undefined because BibTeX has not run yet; those warnings are
# not a defect and must not be read as one.
log = LOG.read_text(errors="replace")
blg = BLG.read_text(errors="replace")
bbl = BBL.read_text(errors="replace")
info = subprocess.run(["pdfinfo", str(PDF)], capture_output=True, text=True).stdout
pages = re.search(r"Pages:\s+(\d+)", info)
n_errors = len(re.findall(r"^!", log, re.M))
n_undef_c = len(re.findall(r"Citation.*undefined", log))
n_undef_r = len(re.findall(r"Reference.*undefined", log))
n_missing = len(re.findall(r"didn't find a database entry", blg))
n_overfull = len(re.findall(r"Overfull", log))
print("    LaTeX errors              : %d" % n_errors)
print("    undefined citations       : %d" % n_undef_c)
print("    undefined references      : %d" % n_undef_r)
print("    missing bib entries       : %d" % n_missing)
print("    overfull hbox             : %d" % n_overfull)
print("    references in .bbl        : %d" % len(re.findall(r"\\bibitem", bbl)))
print("    pages                     : %s" % (pages.group(1) if pages else "?"))

cited = set()
for m in re.finditer(r"\\cite[a-zA-Z]*\{([^}]+)\}", BODY):
    cited.update(k.strip() for k in m.group(1).split(","))
allk = re.findall(r"@\w+\{([^,]+),", BIB)
print("    bibliography entries      : %d" % len(allk))
print("    cited                     : %d" % len(set(allk) & cited))
print("    uncited                   : %d %s"
      % (len([k for k in allk if k not in cited]),
         [k for k in allk if k not in cited] or ""))

floats = 0
for env in ("table", "figure", "equation"):
    for m in re.finditer(r"\\begin\{%s\*?\}(.*?)\\end\{%s\*?\}" % (env, env), BODY, re.S):
        lb = re.search(r"\\label\{([^}]+)\}", m.group(1))
        floats += 1
        if not lb:
            print("    *** float without label: %s" % m.group(1)[:60])
        else:
            refs = len(re.findall(r"\\(?:ref|eqref)\{%s\}" % re.escape(lb.group(1)), BODY))
            if refs == 0:
                print("    *** float never cited: %s" % lb.group(1))
print("    floats/equations          : %d (all labelled and cited if no *** above)" % floats)

# ---------- 7. attribution of named methods ----------
# The audit above reports uncited bibliography ENTRIES. That is not the same defect as a
# METHOD the text names and does not cite, which is what a reader checks: `Ripley's border
# correction`, `Donnelly's correction` and `spatstat` all appeared in the prose with no
# citation, while the same section does cite Theil, Efron, Mann, Sen, Newey-West and
# Prais-Winsten. So the check is on the NAMES, not on the entry list.
#
# ONLY THE FIRST MENTION IS CHECKED, and the citation may sit in the SAME PARAGRAPH rather
# than the same sentence. An earlier version of this check windowed one sentence either side
# of EVERY occurrence, so it flagged "Donnelly flattens it slightly, to 41.9% ..." -- a later,
# purely descriptive mention of a method already attributed 20 lines earlier. A method needs
# to be attributed once; repeating the citation at each mention is not the convention.
print("\n[7] NAMED METHODS ARE ATTRIBUTED")
for name in ("Ripley", "Donnelly", "spatstat", "Besag", "van Lieshout", "Shannon"):
    m = re.search(re.escape(name), BODY, re.I)
    if not m:
        continue
    # the paragraph containing the first mention
    start = BODY.rfind("\n\n", 0, m.start()) + 2
    end = BODY.find("\n\n", m.end())
    para = BODY[start:end if end > 0 else len(BODY)]
    line = BODY.count("\n", 0, m.start()) + 1
    if re.search(r"\\cite[a-zA-Z]*\{", para):
        print("    %-12s first named at main.tex line ~%-4d cited in the same paragraph"
              % (name, line))
    else:
        print("    *** %-12s first named at main.tex line ~%-4d with NO citation in its "
              "paragraph" % (name, line))
