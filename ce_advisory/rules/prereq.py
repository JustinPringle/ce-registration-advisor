"""Prerequisite evaluator.

Returns an outcome *tree* (not a bare bool) so the UI can show only the leaves
that actually block a student. The JavaScript in explorer_template.html mirrors
this exactly; build_explorer.py embeds Python-computed parity cases the page
re-runs on load.

--- CHANGES IN THIS REVISION -------------------------------------------------
Added five leaf operators so the handbook "level gates" (credit/level/year/
set-completion rules on modules that carry no module-specific prerequisite) can
be expressed as data:

    year_of_study        {at_least: N}
    semesters_registered {at_least: N}
    credits_from         {group, members:[...], at_least: N}   # credits in a set
    passed_all           {group, members:[...]}                # every module in a set

`credits_from` / `passed_all` carry an expanded `members` list; the loader
resolves group names (and the computed `preceding_core`) to explicit codes so
the evaluator stays pure — numbers and sets in, outcome out.
------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Outcome:
    ok: bool
    reason: str
    children: list["Outcome"] = field(default_factory=list)
    op: str | None = None
    ref: str | None = None

    def unmet(self) -> list[str]:
        if self.ok:
            return []
        if not self.children:
            return [self.reason]
        out: list[str] = []
        for c in self.children:
            if not c.ok:
                out.extend(c.unmet())
        return out

    def unmet_refs(self) -> list[str]:
        if self.ok:
            return []
        if not self.children:
            return [self.ref] if self.ref else []
        out: list[str] = []
        for c in self.children:
            if not c.ok:
                out.extend(c.unmet_refs())
        return out


@dataclass(frozen=True)
class EvalContext:
    passed_slots: frozenset[str] = frozenset()
    registered_slots: frozenset[str] = frozenset()
    credits_total: int = 0
    credits_by_level: dict[int, int] = field(default_factory=dict)
    # public catalogue credit map (code -> credits); lets credits_from sum a set
    credits_by_code: dict[str, int] = field(default_factory=dict)
    # NEW context inputs for the level gates:
    year_of_study: int = 0
    semesters_registered: int = 0


def evaluate(node: dict[str, Any] | None, ctx: EvalContext) -> Outcome:
    if not node:
        return Outcome(True, "no prerequisites")
    op = next(iter(node))
    arg = node[op]

    if op == "passed":
        ok = arg in ctx.passed_slots
        return Outcome(ok, f"passed {arg}" if ok else f"you have not passed {arg}", ref=arg)

    if op == "registered_for":
        ok = arg in ctx.registered_slots or arg in ctx.passed_slots
        return Outcome(ok, f"registered for {arg}" if ok
                       else f"you must also register for {arg}", ref=arg)

    if op == "credits_at_least":
        ok = ctx.credits_total >= arg
        return Outcome(ok, f"{ctx.credits_total} credits passed (needs {arg})" if ok
                       else f"you need {arg} credits and have {ctx.credits_total} "
                            f"({arg - ctx.credits_total} short)")

    if op == "passed_at_level":
        have = ctx.credits_by_level.get(arg["level"], 0)
        need = arg["credits"]
        ok = have >= need
        return Outcome(ok, f"{have} credits at Level {arg['level']} (needs {need})" if ok
                       else f"you need {need} credits at Level {arg['level']} and have {have}")

    # ---- NEW: level-gate leaves ------------------------------------------
    if op == "year_of_study":
        need = arg["at_least"]
        ok = ctx.year_of_study >= need
        return Outcome(ok, f"in year {ctx.year_of_study} of study (needs {need})" if ok
                       else f"you must be in year {need} of study "
                            f"(currently year {ctx.year_of_study or '—'})")

    if op == "semesters_registered":
        need = arg["at_least"]
        ok = ctx.semesters_registered >= need
        return Outcome(ok, f"{ctx.semesters_registered} semesters registered (needs {need})" if ok
                       else f"you need {need} registered semesters "
                            f"and have {ctx.semesters_registered}")

    if op == "credits_from":
        members = set(arg["members"]) & ctx.passed_slots
        have = sum(ctx.credits_by_code.get(c, 0) for c in members)
        need = arg["at_least"]
        label = arg.get("group", "the set")
        ok = have >= need
        return Outcome(ok, f"{have} credits from {label} (needs {need})" if ok
                       else f"you need {need} credits from {label} and have {have}")

    if op == "passed_all":
        members = list(arg["members"])
        outstanding = [m for m in members if m not in ctx.passed_slots]
        label = arg.get("group", "the set")
        ok = not outstanding
        if ok:
            return Outcome(True, f"passed all of {label}")
        shown = ", ".join(outstanding[:4]) + (" …" if len(outstanding) > 4 else "")
        return Outcome(False,
                       f"{len(outstanding)} of {label} still outstanding: {shown}")

    # ---- combinators ------------------------------------------------------
    if op == "all_of":
        children = [evaluate(n, ctx) for n in arg]
        ok = all(c.ok for c in children)
        return Outcome(ok, "all requirements met" if ok else "not all requirements met",
                       children, op="all_of")

    if op == "any_of":
        children = [evaluate(n, ctx) for n in arg]
        met = next((c for c in children if c.ok), None)
        ok = met is not None
        return Outcome(ok, met.reason if ok
                       else "none of the alternatives is met: "
                            + "; or ".join(c.reason for c in children),
                       children, op="any_of")

    if op == "n_of":
        children = [evaluate(n, ctx) for n in arg["of"]]
        met = sum(1 for c in children if c.ok)
        return Outcome(met >= arg["n"],
                       f"{met} of {arg['n']} required alternatives met",
                       children, op="n_of")

    raise ValueError(f"unknown operator {op!r}")
