#!/usr/bin/env python3
"""Build the explorer from reg_advisor's programme YAMLs — one source of truth.

    python scripts/build_explorer.py [PROGRAMMES_DIR] [OUT.html]

Defaults: reads every ``*.yaml`` under ``vendor/reg_advisor/programmes`` (the
pinned submodule) and writes ``explorer.html``. The page carries only the public
curriculum and rules -- no student data -- so it is safe to commit and to send on.

reg_advisor is authoritative. This script loads each programme through
reg_advisor's own loader, embeds the curriculum and the concession rules
unchanged, and -- the important part -- computes parity cases with reg_advisor's
*engine*. The page re-runs them through its JavaScript mirror (ra_engine.js) and
reports agreement in the footer. If the mirror ever drifts from the advisor, the
footer chip goes red.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RA = ROOT / "vendor" / "reg_advisor" / "scripts"
if not RA.exists():
    sys.exit(f"reg_advisor submodule not found at {RA}\n"
             f"  run:  git submodule update --init")
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
        "rules": {"concession": (rules.get("concession") or {})},
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
    src = Path(argv[1]) if len(argv) > 1 else (ROOT / "vendor/reg_advisor/programmes")
    dest = Path(argv[2]) if len(argv) > 2 else (ROOT / "explorer.html")

    yamls = sorted(src.glob("*.yaml"))
    if not yamls:
        sys.exit(f"no programme YAMLs under {src}")

    programmes, parity = {}, {}
    for y in yamls:
        cur = pl.load_programme(str(y))
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
