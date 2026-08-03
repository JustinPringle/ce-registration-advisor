"""Programme catalogue: modules, prerequisites, curriculum structure.

Loaded from versioned YAML under ``catalogue/<handbook_year>/``. This layer is
public information — it carries no student data and is safe to commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Module:
    code: str
    name: str
    credits: int
    level: int
    offered: tuple[int, ...] = (1,)  # blocks in which the module runs
    kind: str = "degree"  # degree | dp | elective
    prerequisites: dict[str, Any] | None = None
    corequisites: tuple[str, ...] = ()
    prereq_status: str = "unverified"  # handbook | inferred | none | unverified
    substitutes: tuple[str, ...] = ()  # augmented codes that fill this slot

    @property
    def counts_for_credit(self) -> bool:
        return self.kind != "dp"


@dataclass(frozen=True)
class Semester:
    year: int
    block: int
    modules: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"Y{self.year}S{self.block}"


@dataclass(frozen=True)
class Programme:
    code: str
    name: str
    stream: str
    semesters: tuple[Semester, ...]

    def slot_order(self) -> list[str]:
        out: list[str] = []
        for s in self.semesters:
            out.extend(s.modules)
        return out

    def semester_of(self, module_code: str) -> Semester | None:
        for s in self.semesters:
            if module_code in s.modules:
                return s
        return None


@dataclass
class Catalogue:
    handbook_year: int
    modules: dict[str, Module] = field(default_factory=dict)
    programmes: dict[str, Programme] = field(default_factory=dict)

    def module(self, code: str) -> Module:
        try:
            return self.modules[code]
        except KeyError:
            raise KeyError(f"module {code!r} not in catalogue {self.handbook_year}")

    def programme(self, code: str) -> Programme:
        try:
            return self.programmes[code]
        except KeyError:
            raise KeyError(f"programme {code!r} not in catalogue {self.handbook_year}")

    def substitute_map(self) -> dict[str, str]:
        """augmented code -> mainstream slot it fills."""
        return {
            sub: m.code for m in self.modules.values() for sub in m.substitutes
        }

    def unverified_prereqs(self) -> list[str]:
        """Audit hook: which modules still need a handbook check."""
        return sorted(
            m.code
            for m in self.modules.values()
            if m.prereq_status not in {"handbook", "none"}
        )
