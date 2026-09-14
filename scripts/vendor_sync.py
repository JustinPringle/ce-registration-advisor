#!/usr/bin/env python3
"""vendor_sync.py -- refresh the vendored copies of reg_advisor, or check them.

reg_advisor is the source of truth for the engine and for the programme YAMLs.
This repo holds copies so the explorer builds without a submodule, and copies
drift: the engine here sat one decision behind upstream (the passed-mark WAM
concession gate) for weeks with nothing to say so.

    python scripts/vendor_sync.py                 # sync from ../reg_advisor
    python scripts/vendor_sync.py ~/dev/reg_advisor
    python scripts/vendor_sync.py --check         # verify, change nothing

--check compares every vendored file against the recorded hash and exits 1 on a
mismatch, so it can gate a build or a commit. It reports two different faults:
a file edited HERE (never do this -- edit upstream and re-sync), and a lock that
no longer matches the upstream checkout (upstream moved; re-sync).

Copies are byte-identical to upstream on purpose. That is what makes the check a
plain hash comparison; the explanation that used to sit in a header comment on
each file now lives in scripts/_ra/README.md.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "scripts" / "_ra" / "VENDOR.lock"

# upstream path -> path in this repo
FILES: dict[str, str] = {
    "scripts/programme_loader.py":   "scripts/_ra/programme_loader.py",
    "scripts/regadvisor_engine.py":  "scripts/_ra/regadvisor_engine.py",
    "catalogue/modules.yaml":        "catalogue/modules.yaml",
    "programmes/civil.yaml":         "programmes/civil.yaml",
    "programmes/augmented_civil.yaml": "programmes/augmented_civil.yaml",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def upstream_default() -> Path:
    env = os.environ.get("REG_ADVISOR")
    return Path(env).expanduser() if env else ROOT.parent / "reg_advisor"


def git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(repo), *args],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def sync(upstream: Path) -> int:
    if not upstream.exists():
        sys.exit(f"reg_advisor checkout not found at {upstream}\n"
                 f"Pass the path, or set REG_ADVISOR.")
    missing = [s for s in FILES if not (upstream / s).exists()]
    if missing:
        sys.exit("upstream is missing files this repo vendors:\n  "
                 + "\n  ".join(missing))

    lock = {"upstream": str(upstream),
            "commit": git(upstream, "rev-parse", "HEAD"),
            "branch": git(upstream, "rev-parse", "--abbrev-ref", "HEAD"),
            "files": {}}
    changed = []
    for src, dst in FILES.items():
        s, d = upstream / src, ROOT / dst
        before = sha256(d) if d.exists() else None
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(s, d)
        after = sha256(d)
        lock["files"][dst] = {"from": src, "sha256": after}
        if before != after:
            changed.append(dst)

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    print(f"synced from {upstream} @ {lock['commit'][:7]} ({lock['branch']})")
    for c in changed:
        print(f"  updated  {c}")
    if not changed:
        print("  (already up to date)")
    print("\nRebuild the page:  python scripts/build_explorer.py")
    return 0


def check(upstream: Path) -> int:
    if not LOCK.exists():
        sys.exit(f"no {LOCK.name} -- run vendor_sync.py once to create it.")
    lock = json.loads(LOCK.read_text())
    faults = []
    for dst, rec in lock["files"].items():
        p = ROOT / dst
        if not p.exists():
            faults.append(f"missing here: {dst}")
        elif sha256(p) != rec["sha256"]:
            faults.append(f"edited here (edit upstream instead): {dst}")
    stale = []
    if upstream.exists():
        head = git(upstream, "rev-parse", "HEAD")
        if head not in ("unknown", lock.get("commit")):
            stale.append(f"upstream is at {head[:7]}, lock says "
                         f"{str(lock.get('commit'))[:7]}")
        for dst, rec in lock["files"].items():
            s = upstream / rec["from"]
            if s.exists() and sha256(s) != rec["sha256"]:
                stale.append(f"upstream changed: {rec['from']}")
    for f in faults:
        print(f"DRIFT  {f}")
    for s in stale:
        print(f"STALE  {s}")
    if faults or stale:
        print("\nRun: python scripts/vendor_sync.py")
        return 1
    print(f"vendored files match reg_advisor @ {str(lock.get('commit'))[:7]}")
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a != "--check"]
    upstream = Path(args[0]).expanduser() if args else upstream_default()
    return check(upstream) if "--check" in argv else sync(upstream)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
