import re
import tomllib
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

KINDS = ("negative",)
STATUSES = ("draft", "validated")
_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")


@dataclass(frozen=True)
class ForbiddenRemark:
    path: str
    line: int
    concept: str


@dataclass(frozen=True)
class Case:
    """A past pull request, frozen by its base and head commits, and what the reviewer should do."""

    name: str
    pull_request: str
    kind: str
    validated: bool
    base: str
    head: str
    provenance: str
    max_findings: int
    forbidden_remarks: tuple[ForbiddenRemark, ...] = ()


class InvalidCases(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


def load_cases(path: Path) -> list[Case]:
    """Loads the case in a file, or the cases in a directory, one `.toml` file per case.

    Every problem of every file is reported at once, each one prefixed with its file.
    """
    files = sorted(path.glob("*.toml")) if path.is_dir() else [path]
    if not files:
        raise InvalidCases([f"{path}: no case file (*.toml) in this directory"])
    cases, problems = [], []
    for file in files:
        try:
            cases.append(_load(file))
        except InvalidCases as invalid:
            problems += invalid.problems
    if problems:
        raise InvalidCases(problems)
    return cases


def _load(path: Path) -> Case:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise InvalidCases([f"{path}: cannot be read ({error.strerror})"]) from error
    except tomllib.TOMLDecodeError as error:
        raise InvalidCases([f"{path}: not valid TOML: {error}"]) from error
    fields = _Fields(data)
    case = Case(
        name=path.stem,
        pull_request=fields.text("pull_request"),
        kind=fields.choice("kind", KINDS),
        validated=fields.choice("status", STATUSES) == "validated",
        base=fields.sha("base"),
        head=fields.sha("head"),
        provenance=fields.text("provenance"),
        max_findings=fields.count("max_findings"),
        forbidden_remarks=_forbidden_remarks(fields),
    )
    problems = fields.problems + fields.unknown()
    if problems:
        raise InvalidCases([f"{path}: {problem}" for problem in problems])
    return case


def _forbidden_remarks(fields: "_Fields") -> tuple[ForbiddenRemark, ...]:
    remarks = []
    for number, table in enumerate(fields.tables("forbidden_remarks"), start=1):
        remark = _Fields(table, label=f"forbidden remark {number}: ")
        remarks.append(
            ForbiddenRemark(remark.text("path"), remark.line("line"), remark.text("concept"))
        )
        fields.problems += remark.problems + remark.unknown()
    return tuple(remarks)


class _Fields:
    """Reads the fields of a TOML table, collecting every problem rather than stopping at one."""

    def __init__(self, table: dict[str, Any], label: str = "") -> None:
        self._table = table
        self._label = label
        self._read: set[str] = set()
        self.problems: list[str] = []

    def text(self, name: str) -> Any:
        return self._get(
            name, lambda value: isinstance(value, str) and bool(value.strip()), "a non-empty string"
        )

    def choice(self, name: str, choices: Collection[str]) -> Any:
        return self._get(
            name,
            lambda value: value in choices,
            "one of " + ", ".join(repr(choice) for choice in choices),
        )

    def sha(self, name: str) -> Any:
        return self._get(
            name,
            lambda value: isinstance(value, str) and bool(_SHA.fullmatch(value)),
            "a full commit SHA",
        )

    def count(self, name: str) -> Any:
        return self._get(
            name, lambda value: _integer(value) and value >= 0, "a non-negative integer"
        )

    def line(self, name: str) -> Any:
        return self._get(name, lambda value: _integer(value) and value >= 1, "a line number")

    def tables(self, name: str) -> list[dict[str, Any]]:
        if name not in self._table:
            self._read.add(name)
            return []
        tables = self._get(
            name,
            lambda value: isinstance(value, list) and all(isinstance(t, dict) for t in value),
            "an array of tables",
        )
        return tables or []

    def unknown(self) -> list[str]:
        return [
            f"{self._label}unknown field '{name}'" for name in self._table if name not in self._read
        ]

    def _get(self, name: str, valid: Callable[[Any], bool], expectation: str) -> Any:
        self._read.add(name)
        if name not in self._table:
            self.problems.append(f"{self._label}missing field '{name}'")
            return None
        value = self._table[name]
        if not valid(value):
            self.problems.append(f"{self._label}'{name}' must be {expectation}, got {value!r}")
            return None
        return value


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
