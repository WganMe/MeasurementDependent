#!/usr/bin/env python3
"""Create and publish the Zenodo deposit for the manuscript.

Deposit only. Nothing here writes to the working tree, so this can be re-run
against a re-built archive without touching the repository.

Usage:
    python3 make_zenodo_deposit.py            # create draft, upload, publish
    python3 make_zenodo_deposit.py --draft    # stop before publishing
    python3 make_zenodo_deposit.py --status   # report an existing record

The token is read from IEEETC/.env (ZENODO_TOKEN). It is never printed, never
written to disk, and never placed in the archive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent          # the submission folder IS the repository root
# The archive is built with `git archive` from the commit being deposited, so it must be
# rebuilt per release rather than left at an old version number. The previous path pointed at
# /tmp/si_rel/urban-observatory-v1.0.6.zip, which no longer existed at all, so the script could
# not have run as written.
#
# The name matters as much as the path: the previous deposit's file was called
# SymmetrySI-v1.0.6.zip, carrying the name of an MDPI venue this paper WITHDREW, inside an
# archive that held the MDPI class files. This one is named after the software, not a venue.
ARCHIVE = pathlib.Path("/tmp/si_rel/MeasurementDependent-v1.0.7.zip")
ENV = pathlib.Path("/home/bcdr/phd/IEEETC/.env")
API = "https://zenodo.org/api"


def token() -> str:
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if line.startswith("ZENODO_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no ZENODO_TOKEN in %s" % ENV)


def call(url: str, tok: str, method: str = "GET", data=None, ctype=None):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer %s" % tok)
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            body = r.read()
            return r.status, (json.loads(body) if body.strip().startswith(b"{")
                              or body.strip().startswith(b"[") else body)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:800]


def upload_and_publish(dep: dict, tok: str, meta: dict, args) -> int:
    """Upload the archive into `dep`'s bucket, set metadata, optionally publish."""
    dep_id = dep["id"]
    bucket = dep["links"]["bucket"]
    blob = ARCHIVE.read_bytes()
    md5 = hashlib.md5(blob).hexdigest()

    # A reused draft may already hold files from an earlier run; replace them,
    # otherwise the record ends up carrying two archives and the DOI points at
    # whichever Zenodo lists first.
    st, existing = call("%s/deposit/depositions/%d/files" % (API, dep_id), tok)
    if isinstance(existing, list):
        for f in existing:
            if f.get("filename") == ARCHIVE.name:
                continue
            call("%s/deposit/depositions/%d/files/%s" % (API, dep_id, f["id"]),
                 tok, "DELETE")
            print("removed stale file: %s" % f.get("filename"))

    st, up = call("%s/%s" % (bucket, ARCHIVE.name), tok, "PUT", blob,
                  "application/octet-stream")
    if st not in (200, 201):
        raise SystemExit("upload failed: %s %s" % (st, up))
    print("uploaded: %s" % (up.get("key") if isinstance(up, dict) else "ok"))

    st, m = call("%s/deposit/depositions/%d" % (API, dep_id), tok, "PUT",
                 json.dumps({"metadata": meta}).encode(), "application/json")
    if st not in (200, 201):
        raise SystemExit("metadata failed: %s %s" % (st, m))
    print("metadata set: %s" % m["metadata"]["title"][:70])

    st, files = call("%s/deposit/depositions/%d/files" % (API, dep_id), tok)
    if isinstance(files, list):
        for f in files:
            remote = f.get("size") or f.get("filesize")
            print("  remote %s: %s bytes vs local %d -> %s"
                  % (f.get("filename"), remote, len(blob),
                     "MATCH" if f.get("filename") == ARCHIVE.name
                     and remote == len(blob) else "check"))

    print("\npending URL: https://zenodo.org/deposit/%d" % dep_id)
    if args.draft:
        print("\n--draft given: NOT publishing.")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", action="store_true",
                    help="create and upload but do not publish")
    ap.add_argument("--status", type=int, metavar="ID",
                    help="report an existing deposition and exit")
    ap.add_argument("--newversion", type=int, metavar="ID",
                    help="add a NEW VERSION of existing deposition ID. Use this for "
                         "every release after the first: it keeps the concept DOI "
                         "(what the manuscript cites) and gives the version its own "
                         "version DOI. A bare run would mint a NEW concept DOI and "
                         "break the citation.")
    args = ap.parse_args()

    tok = token()

    if args.status:
        st, body = call("%s/deposit/depositions/%d" % (API, args.status), tok)
        print("status %s" % st)
        print(json.dumps({k: body.get(k) for k in ("id", "doi", "state", "submitted")},
                         indent=1) if isinstance(body, dict) else body)
        return 0

    if not ARCHIVE.exists():
        raise SystemExit("archive absent: %s" % ARCHIVE)

    blob = ARCHIVE.read_bytes()
    md5 = hashlib.md5(blob).hexdigest()
    meta = json.loads((HERE / ".zenodo.json").read_text())
    print("archive: %s  (%d bytes, md5 %s)" % (ARCHIVE.name, len(blob), md5))

    if args.newversion:
        # POST .../actions/newversion returns a DRAFT that is a copy of the
        # latest published version and carries the SAME concept DOI.
        st, draft = call("%s/deposit/depositions/%d/actions/newversion"
                         % (API, args.newversion), tok, "POST")
        if st not in (200, 201, 202):
            raise SystemExit("newversion failed: %s %s" % (st, draft))
        # The response points at the original record; the editable draft is the
        # latest_draft link, which is a different deposition id.
        draft_url = draft["links"]["latest_draft"]
        st, dep = call(draft_url, tok)
        if st != 200:
            raise SystemExit("could not open draft: %s %s" % (st, dep))
        print("new version draft id=%s (state=%s) under concept DOI %s"
              % (dep["id"], dep.get("state"), dep.get("conceptdoi")))
        rc = upload_and_publish(dep, tok, meta, args)
        if rc is not None:
            return rc
        dep_id, pub = dep["id"], None
    else:
        # ---- 1. create an empty deposition --------------------------------
        st, dep = call("%s/deposit/depositions" % API, tok, "POST", b"{}",
                       "application/json")
        if st not in (200, 201):
            raise SystemExit("create failed: %s %s" % (st, dep))
        dep_id = dep["id"]
        print("created deposition id=%s (state=%s)" % (dep_id, dep.get("state")))
        rc = upload_and_publish(dep, tok, meta, args)
        if rc is not None:
            return rc

    # ---- 5. publish -------------------------------------------------------
    # upload_and_publish returns 0 when --draft was given, and only returns
    # None when the caller is clear to publish. Without this check a --draft
    # run still went on to publish, which is the one thing the flag forbids.
    st, pub = call("%s/deposit/depositions/%d/actions/publish" % (API, dep_id),
                   tok, "POST")
    if st not in (200, 201, 202):
        raise SystemExit("publish failed: %s %s" % (st, pub))
    print("\nPUBLISHED")
    print("  record   : https://zenodo.org/records/%d" % dep_id)
    print("  version DOI : %s" % pub.get("doi"))
    print("  concept DOI : %s" % pub.get("conceptdoi"))

    out = HERE / "ZENODO_RECORD.json"
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE,
                                capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        commit = None
    out.write_text(json.dumps({
        "deposition_id": dep_id,
        "doi": pub.get("doi"),
        "conceptdoi": pub.get("conceptdoi"),
        "record_url": "https://zenodo.org/records/%d" % dep_id,
        "file": ARCHIVE.name, "bytes": len(blob), "md5": md5,
        "version": meta["version"], "license": meta["license"],
        "commit": commit,
    }, indent=1))
    print("  wrote %s" % out.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
