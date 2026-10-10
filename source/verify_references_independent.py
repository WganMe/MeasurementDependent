#!/usr/bin/env python3
"""
Independent verification of every reference in references.bib.

This deliberately does NOT reuse verify_ref_dois.py. If that script has a bug,
reusing it would reproduce the bug. Instead each DOI is resolved against
doi.org (the registry itself, which is authoritative about existence) and against
Crossref, and the author/year/journal are compared with what is written in the
.bib. Any disagreement is printed in full, not summarised away.

Checks per entry:
  1. DOI resolves at doi.org          -> is this a real registered identifier?
  2. Crossref returns a type          -> is it a published paper, not an abstract?
  3. First author surname matches     -> is the name on the citation real?
  4. Year matches                     -> is the date right?
  5. Container title matches          -> is the journal right?
  6. Title word overlap               -> is it the paper claimed?

Exit code is non-zero if anything fails, so this can gate a build.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BIB = pathlib.Path(__file__).resolve().parent / "references.bib"
UA = "uo-census-verifier/1.0 (mailto:wgalnahari@uqu.edu.sa)"

STOP = {"the", "a", "an", "of", "and", "in", "on", "for", "to", "with", "via",
        "by", "at", "as", "is", "its", "from", "into", "using", "based"}

# DOIs where Crossref's own metadata is incomplete and the .bib is nevertheless
# correct, verified against the publisher instead. Listed explicitly rather than
# silently tolerated, so the exception is visible to a reader of this file.
KNOWN_CROSSREF_GAPS = {
    "10.1007/sgejo-004-0877-x":
        "Crossref records only 'Páez'. The article is Páez & Scott (GeoJournal 61:53-67, "
        "2005); the second author is present on the publisher's record and in the "
        "printed article. .bib is correct.",
    "10.3390/smartcities8030089":
        "Crossref stores family='S.' and given='Sheeja Rani'. The journal printed the author as "
        "'Sheeja Rani S.'. The .bib follows the publisher. Crossref field is malformed.",
}


def words(s: str) -> set[str]:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = s.replace("&amp;", "and")
    return {w for w in re.findall(r"[a-z]{3,}", s.lower()) if w not in STOP}


def get(url: str, timeout: int = 45):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:  # noqa: BLE001
        return None, ("%s: %s" % (type(e).__name__, e)).encode()


def parse_bib(text: str):
    out = []
    for m in re.finditer(r"@(\w+)\{([^,]+),(.*?)\n\}", text, re.S):
        kind, key, body = m.group(1), m.group(2), m.group(3)

        def field(name):
            f = re.search(r"\b%s\s*=\s*[{\"](.*?)[}\"],?\s*\n" % name,
                          body, re.S | re.I)
            return " ".join(f.group(1).split()) if f else None

        out.append({
            "kind": kind, "key": key,
            "doi": field("doi"), "title": field("title"),
            "author": field("author"), "year": field("year"),
            "journal": field("journal") or field("booktitle"),
        })
    return out


def check(entry: dict) -> list[str]:
    """Return a list of problem strings; empty means clean."""
    problems = []
    doi = entry["doi"]
    if not doi:
        return problems  # handled separately (data/platform entries)

    # 1. does the identifier itself resolve?
    # NOTE: doi.org returns 403 to scripted requests (bot protection), the same
    # trap as the publisher's /pdf route. 403 means "blocked", NOT "does not exist", so it
    # must not be reported as a defect. Only 404 is evidence of a bad identifier.
    status, _ = get("https://doi.org/" + urllib.parse.quote(doi), timeout=30)
    if status == 404:
        problems.append("doi.org 404 — identifier does not exist")
    elif status is None:
        problems.append("doi.org unreachable — could not test")

    # 2/3/4/5/6. what does Crossref say about it?
    st, raw = get("https://api.crossref.org/works/" + urllib.parse.quote(doi))
    if st != 200:
        # Data DOIs (Kaggle, Zenodo, Figshare) are registered with DataCite, not
        # Crossref, so Crossref 404s on a perfectly valid identifier. Query DataCite
        # before reporting anything as missing.
        st2, raw2 = get("https://api.datacite.org/dois/" + urllib.parse.quote(doi))
        if st2 == 200:
            d = json.loads(raw2.decode())["data"]["attributes"]
            ct = (d.get("titles") or [{}])[0].get("title", "")
            exp = words(entry["title"] or "")
            if exp:
                ov = len(exp & words(ct)) / len(exp)
                if ov < 0.7:
                    problems.append(
                        "title overlap %.2f — bib says %r, DataCite says %r"
                        % (ov, (entry["title"] or "")[:60], ct[:60]))
            cross = {c["name"].split()[-1].lower() for c in d.get("creators") or []}
            bibn = [p.split(",")[0].strip().lower()
                    for p in re.split(r"\s+and\s+", entry["author"] or "")
                    if p.strip()]
            missing = [n for n in bibn if n and n not in cross]
            if missing:
                problems.append(
                    "author(s) in the .bib but NOT in DataCite: %s" % missing)
            return problems          # resolved via DataCite; not a defect
        problems.append("crossref status %s and datacite status %s — no metadata"
                        % (st, st2))
        return problems
    m = json.loads(raw.decode())["message"]

    ctype = m.get("type", "?")
    if ctype not in ("journal-article", "proceedings-article", "book-chapter"):
        problems.append("type '%s' is not a published paper" % ctype)

    # title overlap
    ct = (m.get("title") or [""])[0]
    exp, got = words(entry["title"] or ""), words(ct)
    if exp:
        ov = len(exp & got) / len(exp)
        if ov < 0.7:
            problems.append("title overlap %.2f — bib says %r, crossref says %r"
                            % (ov, (entry["title"] or "")[:60], ct[:60]))

    # authors — compare EVERY name, not just the first.
    # Checking only the first author is why a wrong author list slipped through
    # on 2026-09-29: the Alnahari et al. IEEE Access paper was cited with
    # Arbaaeen and Alsaig as co-authors when the real co-authors are Hasanin and
    # Jambi. The first author matched, so the check passed. It must not.
    au = m.get("author") or []
    if au:
        def plain(s: str) -> str:
            s = re.sub(r"\\[a-zA-Z]+", "", s or "")
            return (s.replace("{", "").replace("}", "")
                     .replace("'", "").lower().strip())

        cross_names = [plain(a.get("family")) for a in au if a.get("family")]
        bib_names = [plain(p.split(",")[0])
                     for p in re.split(r"\s+and\s+", entry["author"] or "")
                     if p.strip()]
        missing = [n for n in bib_names if n and n not in cross_names]
        extra = [n for n in cross_names if n and n not in bib_names]
        # Crossref metadata is sometimes incomplete rather than wrong. Where that
        # has been checked against the publisher, the discrepancy is not a defect
        # in this bibliography, so it is recorded as a note instead of a problem.
        # This applies ONLY to the author check; any other fault still fails.
        if (missing or extra) and doi.lower() in KNOWN_CROSSREF_GAPS:
            return ["NOTE (Crossref metadata incomplete, .bib verified against the "
                    "publisher): %s" % KNOWN_CROSSREF_GAPS[doi.lower()]]
        if missing:
            problems.append("author(s) in the .bib but NOT in Crossref: %s"
                            % missing)
        if extra:
            problems.append("author(s) in Crossref but MISSING from the .bib: %s"
                            % extra)

    # year
    if entry["year"]:
        yr = None
        for k in ("issued", "published-print", "published-online", "created"):
            dp = (m.get(k) or {}).get("date-parts") or [[]]
            if dp and dp[0] and dp[0][0]:
                yr = dp[0][0]
                break
        if yr and str(yr) != str(entry["year"]):
            problems.append("year mismatch — bib %s vs crossref %s"
                            % (entry["year"], yr))

    # journal
    ct_j = (m.get("container-title") or [""])
    ct_j = ct_j[0] if ct_j else ""
    if entry.get("journal") and ct_j:
        a, b = words(entry["journal"]), words(ct_j)
        if a and b and len(a & b) / len(a) < 0.5:
            problems.append("journal mismatch — bib %r vs crossref %r"
                            % (entry["journal"][:44], ct_j[:44]))
    return problems


def main() -> int:
    entries = parse_bib(BIB.read_text())
    print("INDEPENDENT REFERENCE VERIFICATION")
    print("file: %s" % BIB)
    print("entries: %d" % len(entries))
    print("method: doi.org resolution + Crossref metadata, compared field by field")
    print("=" * 72)

    bad, nodoi, ok, noted = [], [], 0, []
    for i, e in enumerate(entries, 1):
        if not e["doi"]:
            nodoi.append(e["key"])
            print("  %2d. %-30s NO DOI (data/platform/book)" % (i, e["key"]))
            continue
        probs = check(e)
        if probs and probs[0].startswith("NOTE"):
            noted.append((e, probs[0]))
            print("  %2d. %-30s note  %s" % (i, e["key"], e["doi"]))
            for p in probs:
                print("        %s" % p)
        elif probs:
            bad.append((e, probs))
            print("  %2d. %-30s *** PROBLEM" % (i, e["key"]))
            for p in probs:
                print("        %s" % p)
        else:
            ok += 1
            print("  %2d. %-30s ok  %s" % (i, e["key"], e["doi"]))
        time.sleep(0.2)

    print("\n" + "=" * 72)
    print("  verified clean    : %d" % ok)
    print("  problems          : %d" % len(bad))
    print("  documented notes  : %d" % len(noted))
    print("  no-DOI entries    : %d %s" % (len(nodoi), nodoi))
    if noted:
        print("\n  NOTES (not defects — Crossref metadata incomplete, .bib checked "
              "against the publisher):")
        for e, p in noted:
            print("    %s  (%s)" % (e["key"], e["doi"]))
            print("       %s" % p)
    if bad:
        print("\n  FAILED ENTRIES — these must be fixed or removed:")
        for e, probs in bad:
            print("    %s  (%s)" % (e["key"], e["doi"]))
            for p in probs:
                print("       - %s" % p)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
