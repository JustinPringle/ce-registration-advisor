#!/usr/bin/env python3
"""Generate the catalogue explorer: one standalone HTML file, no server.

    python scripts/build_explorer.py catalogue/2027 explorer.html

The page is built *from* the YAML, so it cannot drift from the catalogue. It
carries no student data — only the public catalogue — and is safe to commit
and to send to Dillip.

The page re-implements the prerequisite evaluator in JavaScript. To keep that
mirror honest, this script runs a set of scenarios through the Python
evaluator and embeds the expected results; the page re-runs them on load and
reports parity in the footer. Python remains authoritative.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ce_advisory.catalogue.loader import load_catalogue  # noqa: E402
from ce_advisory.rules.prereq import EvalContext, evaluate  # noqa: E402

TEMPLATE = Path(__file__).with_name("explorer_template.html")


def catalogue_payload(cat) -> dict:
    modules = {
        code: {
            "name": m.name,
            "credits": m.credits,
            "level": m.level,
            "offered": list(m.offered),
            "kind": m.kind,
            "prerequisites": m.prerequisites,
            "corequisites": list(m.corequisites),
            "prereqStatus": m.prereq_status,
            "substitutes": list(m.substitutes),
        }
        for code, m in cat.modules.items()
    }
    programmes = {
        code: {
            "name": p.name,
            "stream": p.stream,
            "semesters": [
                {"year": s.year, "block": s.block, "modules": list(s.modules)}
                for s in p.semesters
            ],
        }
        for code, p in cat.programmes.items()
    }
    # progression: the template's min-progression gauge reads
    # CATALOGUE.progression.streams[stream][sem]; electives/choices drive the
    # elective slots and the Y2S1 pick (choices supersedes the template's
    # hand-written CHOICES fallback once present).
    progression = {
        "normalSemesterLoad": cat.progression.get("normal_semester_load", 72),
        "streams": {
            stream: {str(sem): row for sem, row in (rows or {}).items()}
            for stream, rows in (cat.progression.get("streams") or {}).items()
        },
    }
    return {
        "handbookYear": cat.handbook_year,
        "modules": modules,
        "programmes": programmes,
        "unverified": cat.unverified_prereqs(),
        "progression": progression,
        "electives": cat.progression.get("electives", []),
        "choices": cat.progression.get("choices", []),
    }


def parity_cases(cat) -> list[dict]:
    """Scenarios evaluated in Python; the page must reproduce them exactly.

    Covers every operator the catalogue uses, including the level-gate leaves
    (year_of_study, semesters_registered, credits_from, passed_all,
    passed_at_level), so the footer chip guards the whole evaluator — not just
    the simple `passed` rules.
    """
    levels = {c: m.level for c, m in cat.modules.items()}
    credits = {c: m.credits for c, m in cat.modules.items()}

    FY = ["CHEM181", "ENCH1TC", "ENME1DR", "MATH131", "MATH132", "PHYS151",
          "CHEM191", "ENCV1ED", "ENME1EM", "MATH141", "MATH142", "PHYS152"]
    capstone = cat.module("ENCV4DE").prerequisites["passed_all"]["members"]

    # (module, passed, year_of_study, semesters_registered)
    scenarios = [
        ("CHEM181", [], 1, 1),
        ("ENCV2SA", ["MATH141"], 2, 2),
        ("MATH248", ["MATH141", "MATH238"], 2, 4),
        ("ENCV3FA", ["ENCV2FL"], 3, 4),
        ("ENCV3TT", [], 2, 2),
        ("ENCV3TT", [], 3, 2),
        ("ENPD7PP", FY, 3, 6),
        ("ENPD7PP", FY, 4, 6),
        ("ENSV2SE", ["MATH131", "MATH132", "PHYS151"], 2, 2),
        ("ENSV2SE", ["CHEM181", "ENCH1TC", "ENME1DR", "MATH131", "MATH132", "PHYS151"], 2, 2),
        ("ENSV2SE", ["CHEM181", "ENCH1TC", "ENME1DR", "MATH131", "MATH132", "PHYS151"], 2, 1),
        ("ENCV3G1", FY, 3, 4),
        ("ENCV3G1", FY + ["ENCV2SA", "ENCV2SB"], 3, 4),
        ("ENCV4DE", [], 4, 8),
        ("ENCV4DE", capstone, 4, 8),
    ]

    cases = []
    for code, passed, yos, sems in scenarios:
        by_level: dict[int, int] = {}
        by_code: dict[str, int] = {}
        for slot in passed:
            by_level[levels[slot]] = by_level.get(levels[slot], 0) + credits[slot]
            by_code[slot] = credits[slot]
        ctx = EvalContext(
            passed_slots=frozenset(passed),
            credits_total=sum(credits[s] for s in passed),
            credits_by_level=by_level,
            credits_by_code=by_code,
            year_of_study=yos,
            semesters_registered=sems,
        )
        out = evaluate(cat.module(code).prerequisites, ctx)
        cases.append({
            "module": code,
            "passed": sorted(passed),
            "credits": sum(credits[s] for s in passed),
            "creditsByLevel": {str(k): v for k, v in by_level.items()},
            "yearOfStudy": yos,
            "semestersRegistered": sems,
            "ok": out.ok,
            "unmet": out.unmet(),
        })
    return cases


def main(argv: list[str]) -> int:
    src = Path(argv[1]) if len(argv) > 1 else Path("catalogue/2027")
    dest = Path(argv[2]) if len(argv) > 2 else Path("explorer.html")

    cat = load_catalogue(src)
    html = TEMPLATE.read_text()
    html = html.replace("/*__CATALOGUE__*/null", json.dumps(catalogue_payload(cat)))
    html = html.replace("/*__PARITY__*/null", json.dumps(parity_cases(cat)))
    dest.write_text(html)

    print(f"Wrote {dest} — catalogue {cat.handbook_year}, "
          f"{len(cat.modules)} modules, {len(parity_cases(cat))} parity cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
