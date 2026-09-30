import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    description: str
    base: str
    head: str
    max_findings: int
    forbidden_remarks: tuple[ForbiddenRemark, ...] = ()


class InvalidCases(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


def load_cases(*paths: Path) -> list[Case]:
    """Loads the cases of files or directories, one `.toml` file per case.

    Every problem of every file is reported at once, each one prefixed with its file.
    """
    cases, problems = [], []
    for path in paths:
        files = sorted(path.glob("*.toml")) if path.is_dir() else [path]
        if not files:
            problems.append(f"{path}: no case file (*.toml) in this directory")
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
        description=fields.text("description"),
        base=fields.sha("base"),
        head=fields.sha("head"),
        max_findings=fields.count("max_findings"),
        forbidden_remarks=tuple(
            ForbiddenRemark(remark.text("path"), remark.line("line"), remark.text("concept"))
            for remark in fields.tables("forbidden_remarks", label="forbidden remark")
        ),
    )
    if problems := fields.problems:
        raise InvalidCases([f"{path}: {problem}" for problem in problems])
    return case


class _Fields:
    """Reads the fields of a TOML table, collecting every problem rather than stopping at one."""

    def __init__(self, table: dict[str, Any], label: str = "") -> None:
        self._table = table
        self._label = label
        self._read: set[str] = set()
        self._problems: list[str] = []
        self._tables: list[_Fields] = []

    @property
    def problems(self) -> list[str]:
        """Problems of the fields read so far, of unknown fields, and of the tables read."""
        unknown = [
            f"{self._label}unknown field '{name}'" for name in self._table if name not in self._read
        ]
        return self._problems + unknown + [problem for t in self._tables for problem in t.problems]

    def text(self, name: str) -> Any:
        return self._get(
            name, lambda value: isinstance(value, str) and bool(value.strip()), "a non-empty string"
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

    def tables(self, name: str, label: str) -> list["_Fields"]:
        """Readers of an optional array of tables, each labelled with its number in problems."""
        self._read.add(name)
        if name not in self._table:
            return []
        tables = self._get(
            name,
            lambda value: isinstance(value, list) and all(isinstance(t, dict) for t in value),
            "an array of tables",
        )
        self._tables = [
            _Fields(table, label=f"{self._label}{label} {number}: ")
            for number, table in enumerate(tables or [], start=1)
        ]
        return self._tables

    def _get(self, name: str, valid: Callable[[Any], bool], expectation: str) -> Any:
        self._read.add(name)
        if name not in self._table:
            self._problems.append(f"{self._label}missing field '{name}'")
            return None
        value = self._table[name]
        if not valid(value):
            self._problems.append(f"{self._label}'{name}' must be {expectation}, got {value!r}")
            return None
        return value


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
