#!/usr/bin/env python3
"""Build the explorer from reg_advisor's programme YAMLs — one source of truth.

    python scripts/build_explorer.py [PROGRAMMES_DIR] [OUT.html]

Defaults: reads every ``*.yaml`` under ``programmes/`` and writes
``explorer.html``. The page carries only the public curriculum and rules -- no
student data -- so it is safe to commit and to send on.

reg_advisor is the source of truth. Copy its ``programmes/*.yaml`` into this
folder whenever they change; the engine logic lives, copied once, under
``scripts/_ra/``. This script loads each programme through reg_advisor's loader,
embeds the curriculum and concession rules unchanged, and -- the important part
-- computes parity cases with reg_advisor's *engine*. The page re-runs them
through its JavaScript mirror (ra_engine.js) and reports agreement in the footer.
If the mirror ever drifts from the engine, the footer chip goes red.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RA = ROOT / "scripts" / "_ra"          # vendored reg_advisor engine (copied once)
if not RA.exists():
    sys.exit(f"reg_advisor engine not found at {RA}")
sys.path.insert(0, str(RA))

import programme_loader as pl          # noqa: E402  (from the submodule)
import regadvisor_engine as eng        # noqa: E402

TEMPLATE = Path(__file__).with_name("explorer_template.html")
ENGINE_JS = Path(__file__).with_name("ra_engine.js")

PROFILES = [
    {},
    {"CHEM181": 80, "ENCH1TC": 80, "ENME1DR": 80, "MATH131": 42,
     "MATH132": 80, "PHYS151": 80},
    {"ENME1DR": 48},
    {"MATH131": 80, "MATH132": 80, "MATH141": 80, "MATH142": 80,
     "PHYS151": 80, "PHYS152": 80, "CHEM181": 80, "CHEM191": 80,
     "ENME1DR": 80, "ENME1EM": 80, "ENCV1ED": 80},
]


def programme_payload(cur: dict) -> dict:
    prog = cur.get("programme", {})
    rules = cur.get("rules") or {}
    ers = (rules.get("ers") or {})
    progression = {str(k): v for k, v in (ers.get("progression") or {}).items()}
    modules = [
        {
            "code": m["code"], "name": m.get("name", m["code"]),
            "credits": m.get("credits", 0),
            "year": m.get("year", 0), "sem": m.get("sem", 0),
            "prereqs": m.get("prereqs") or [],
            "coreqs": m.get("coreqs") or [],
            "isDp": bool(m.get("is_dp")),
            "type": m.get("type", "prescribed"),
            "choice": m.get("choice") or None,
            "level": eng.code_level(m["code"]),
        }
        for m in cur.get("modules", [])
    ]
    equivalences = [[a, b] for a, b in (cur.get("equivalences") or [])]
    return {
        "code": prog.get("code", "PROG"),
        "name": prog.get("name", prog.get("code", "Programme")),
        "stream": "augmented" if "augment" in prog.get("name", "").lower() else "mainstream",
        "passMark": 50,
        # concession drives the verdict; credit_cap and electives are read only by
        # the printed advisory record, which states the load and elective rules
        # the student's plan is measured against.
        "rules": {"concession": (rules.get("concession") or {}),
                  "credit_cap": (rules.get("credit_cap") or {}),
                  "electives": (rules.get("electives") or {})},
        "progression": progression,
        "equivalences": equivalences,
        "modules": modules,
    }


def parity_for(cur: dict) -> list[dict]:
    eq = [(a, b) for a, b in (cur.get("equivalences") or [])]
    mods = cur.get("modules", [])
    by_code = {m["code"]: m for m in mods}
    cases = []
    for prof in PROFILES:
        res = [{"course_code": k, "mark": v, "credits": by_code.get(k, {}).get("credits", 0)}
               for k, v in prof.items()]
        tx = eng.index_transcript(res, equivalences=eq)
        adv = eng.eval_advice(cur, tx)
        buckets = {}
        for bucket in ("can_register", "concession_possible", "cannot_register",
                       "needs_review", "passed"):
            for m in adv[bucket]:
                buckets[m["code"]] = bucket
        cases.append({"marks": prof, "gpa": tx["gpa"], "buckets": buckets})
    return cases


def main(argv: list[str]) -> int:
    src = Path(argv[1]) if len(argv) > 1 else (ROOT / "programmes")
    dest = Path(argv[2]) if len(argv) > 2 else (ROOT / "explorer.html")

    yamls = sorted(src.glob("*.yaml"))
    if not yamls:
        sys.exit(f"no programme YAMLs under {src}")

    # Mainstream first: the page opens on the first key, and alphabetical file
    # order would otherwise land every student on the augmented programme.
    loaded = [(y, pl.load_programme(str(y))) for y in yamls]
    loaded.sort(key=lambda pair: (
        "augment" in (pair[1].get("programme", {}).get("name", "").lower()),
        pair[0].name))

    programmes, parity = {}, {}
    for _y, cur in loaded:
        pay = programme_payload(cur)
        programmes[pay["code"]] = pay
        parity[pay["code"]] = parity_for(cur)

    payload = {"programmes": programmes,
               "source": "reg_advisor (submodule) — single source of truth"}

    html = TEMPLATE.read_text()
    html = html.replace("/*__RA_ENGINE__*/", ENGINE_JS.read_text())
    html = html.replace("/*__PAYLOAD__*/null", json.dumps(payload))
    html = html.replace("/*__PARITY__*/null", json.dumps(parity))
    dest.write_text(html)

    total = sum(len(p["modules"]) for p in programmes.values())
    print(f"Wrote {dest} — {len(programmes)} programme(s), {total} modules, "
          f"parity from reg_advisor engine over {len(PROFILES)} profiles each.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
