"""Load and validate the catalogue YAML.

Validation happens once, at load. Every reference must resolve.

--- CHANGES IN THIS REVISION -------------------------------------------------
The loader now also reads progression.yaml's `groups` and `level_gates`, and
resolves them into module prerequisites:

  * a module whose prerequisites are `{gate: NAME}` gets the named gate
    expression inlined from progression.yaml;
  * inside any gate, `passed_all: <name>` and `credits_from: {group: <name>}`
    have their group expanded to an explicit `members: [...]` list;
  * the special group `preceding_core` is computed per module: every core
    (degree, non-dp, non-elective) module in an *earlier* semester of the
    module's programme.

After resolution the evaluator only ever sees explicit sets and numbers, so
the JS mirror needs no group knowledge. The raw YAML stays readable.
------------------------------------------------------------------------------
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from .catalogue import Catalogue, Module, Programme, Semester

VALID_NODES = {
    "passed", "registered_for", "all_of", "any_of", "n_of",
    "credits_at_least", "passed_at_level",
    # NEW level-gate leaves:
    "year_of_study", "semesters_registered", "credits_from", "passed_all",
    # macro (resolved away at load):
    "gate",
}
VALID_KINDS = {"degree", "dp", "elective"}
VALID_PREREQ_STATUS = {"handbook", "inferred", "none", "unverified"}


class CatalogueError(ValueError):
    """Raised when the YAML is structurally wrong or internally inconsistent."""


def load_catalogue(directory: str | Path) -> Catalogue:
    directory = Path(directory)
    year = _handbook_year(directory)

    modules = _load_modules(directory / "modules.yaml")
    programmes = _load_programmes(directory / "programmes.yaml", modules)

    prog_path = directory / "progression.yaml"
    progression = _read_yaml(prog_path) if prog_path.exists() else {}
    groups = {k: tuple(v) for k, v in (progression.get("groups") or {}).items()}
    level_gates = progression.get("level_gates") or {}

    cat = Catalogue(
        handbook_year=year, modules=modules, programmes=programmes,
        groups=groups, level_gates=level_gates, progression=progression,
    )
    _resolve_gates(cat)
    _validate_references(cat)
    return cat


def _handbook_year(directory: Path) -> int:
    try:
        return int(directory.name)
    except ValueError:
        raise CatalogueError(
            f"catalogue directory name must be a handbook year, got {directory.name!r}"
        )


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise CatalogueError(f"missing catalogue file: {path}")
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def _load_modules(path: Path) -> dict[str, Module]:
    raw = _read_yaml(path)
    modules: dict[str, Module] = {}
    for code, spec in raw.items():
        spec = spec or {}
        kind = spec.get("kind", "degree")
        if kind not in VALID_KINDS:
            raise CatalogueError(f"{code}: kind {kind!r} not in {sorted(VALID_KINDS)}")
        status = spec.get("prereq_status", "unverified")
        if status not in VALID_PREREQ_STATUS:
            raise CatalogueError(f"{code}: prereq_status {status!r} invalid")
        modules[code] = Module(
            code=code,
            name=spec.get("name", code),
            credits=int(spec.get("credits", 0)),
            level=int(spec.get("level", 0)),
            offered=tuple(spec.get("offered", [1])),
            kind=kind,
            prerequisites=spec.get("prerequisites"),
            corequisites=tuple(spec.get("corequisites", ())),
            prereq_status=status,
            substitutes=tuple(spec.get("substitutes", ())),
        )
    return modules


def _load_programmes(path: Path, modules: dict[str, Module]) -> dict[str, Programme]:
    raw = _read_yaml(path)
    programmes: dict[str, Programme] = {}
    for code, spec in raw.items():
        spec = spec or {}
        sems = tuple(
            Semester(year=int(s["year"]), block=int(s["block"]),
                     modules=tuple(s["modules"]))
            for s in spec.get("semesters", [])
        )
        programmes[code] = Programme(
            code=code, name=spec.get("name", code),
            stream=spec.get("stream", "mainstream"), semesters=sems,
        )
    return programmes


# --------------------------------------------------------------------------
# gate + group resolution
# --------------------------------------------------------------------------
def _resolve_gates(cat: Catalogue) -> None:
    """Inline `{gate: NAME}` references and expand group names in place."""
    for code, m in list(cat.modules.items()):
        pre = m.prerequisites
        if not isinstance(pre, dict):
            continue
        if "gate" in pre:
            name = pre["gate"]
            if name not in cat.level_gates:
                raise CatalogueError(f"{code}: unknown gate {name!r}")
            expr = copy.deepcopy(cat.level_gates[name])
            expr = _expand_groups(expr, cat, module_code=code, gate=name)
            object.__setattr__(m, "prerequisites", expr)
        else:
            object.__setattr__(m, "prerequisites",
                               _expand_groups(copy.deepcopy(pre), cat, code, gate=None))


def _expand_groups(node: Any, cat: Catalogue, module_code: str, gate: str | None) -> Any:
    if not isinstance(node, dict):
        return node
    op = next(iter(node))
    arg = node[op]

    if op == "passed_all":
        members = _members(arg, cat, module_code)
        return {"passed_all": {"group": _label(arg), "members": members}}

    if op == "credits_from":
        members = _members(arg["group"], cat, module_code)
        return {"credits_from": {"group": arg["group"], "members": members,
                                 "at_least": arg["at_least"]}}

    if op in ("all_of", "any_of"):
        return {op: [_expand_groups(n, cat, module_code, gate) for n in arg]}
    if op == "n_of":
        return {"n_of": {"n": arg["n"],
                         "of": [_expand_groups(n, cat, module_code, gate) for n in arg["of"]]}}
    return node


def _label(arg: Any) -> str:
    return arg if isinstance(arg, str) else arg.get("group", "the set")


def _members(name: Any, cat: Catalogue, module_code: str) -> list[str]:
    if isinstance(name, list):
        return list(name)
    if name == "preceding_core":
        return _preceding_core(cat, module_code)
    if name in cat.groups:
        return list(cat.groups[name])
    raise CatalogueError(f"{module_code}: unknown group {name!r}")


def _preceding_core(cat: Catalogue, module_code: str) -> list[str]:
    """Every core module in a semester strictly before module_code's semester."""
    prog = next((p for p in cat.programmes.values()
                 if p.semester_of(module_code)), None)
    if prog is None:
        raise CatalogueError(
            f"{module_code}: gate uses preceding_core but module is in no programme")
    here = prog.semester_of(module_code)
    idx = {s.key: i for i, s in enumerate(prog.semesters)}
    cutoff = idx[here.key]
    out: list[str] = []
    for s in prog.semesters:
        if idx[s.key] >= cutoff:
            continue
        for c in s.modules:
            m = cat.modules.get(c)
            if m and m.kind == "degree":
                out.append(c)
    return out


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------
def _validate_references(cat: Catalogue) -> None:
    known = set(cat.modules)
    for code, m in cat.modules.items():
        if m.prerequisites:
            _validate_node(m.prerequisites, code, known)
        for cor in m.corequisites:
            if cor not in known:
                raise CatalogueError(f"{code}: corequisite {cor!r} not in catalogue")


def _validate_node(node: dict, code: str, known: set[str]) -> None:
    if not isinstance(node, dict):
        raise CatalogueError(f"{code}: prerequisite node must be a mapping, got {node!r}")
    op = next(iter(node))
    if op not in VALID_NODES:
        raise CatalogueError(f"{code}: unknown prerequisite operator {op!r}")
    arg = node[op]
    if op in ("passed", "registered_for"):
        if arg not in known:
            raise CatalogueError(f"{code}: prerequisite {arg!r} not in catalogue")
    elif op in ("all_of", "any_of"):
        for n in arg:
            _validate_node(n, code, known)
    elif op == "n_of":
        for n in arg["of"]:
            _validate_node(n, code, known)
    elif op in ("passed_all", "credits_from"):
        for member in arg["members"]:
            if member not in known:
                raise CatalogueError(f"{code}: {op} member {member!r} not in catalogue")
