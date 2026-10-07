import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_SHA = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class ForbiddenRemark:
    path: str
    line: int
    concept: str


@dataclass(frozen=True)
class ExpectedDefect:
    """A defect the pull request introduced, which the change linked by `fix` corrected afterwards.

    `escaped_review` tells whether the human review of the pull request let it through.
    """

    path: str
    line: int
    concept: str
    fix: str
    escaped_review: bool


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
    expected_defects: tuple[ExpectedDefect, ...] = ()


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


def _load(path):
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise InvalidCases([f"{path}: cannot be read ({error.strerror})"]) from error
    except tomllib.TOMLDecodeError as error:
        raise InvalidCases([f"{path}: not valid TOML: {error}"]) from error
    if problems := _case_problems(data):
        raise InvalidCases([f"{path}: {problem}" for problem in problems])
    return Case(
        name=path.stem,
        pull_request=data["pull_request"],
        description=data["description"],
        base=data["base"],
        head=data["head"],
        max_findings=data["max_findings"],
        forbidden_remarks=tuple(
            ForbiddenRemark(**remark) for remark in data.get("forbidden_remarks", [])
        ),
        expected_defects=tuple(
            ExpectedDefect(**defect) for defect in data.get("expected_defects", [])
        ),
    )


def _case_problems(data):
    problems = _problems(data, _CASE_FIELDS, _OPTIONAL_CASE_FIELDS)
    for field, label, rules in _TABLES:
        items = data.get(field, [])
        if _is_list_of_tables(items):
            for number, item in enumerate(items, start=1):
                problems += _problems(item, rules, {}, label=f"{label} {number}: ")
    defects, ceiling = data.get("expected_defects", []), data.get("max_findings")
    if isinstance(defects, list) and _is_count(ceiling) and ceiling < len(defects):
        problems.append(
            f"'max_findings' must allow the {len(defects)} expected defect(s), got {ceiling}"
        )
    return problems


def _problems(data, required, optional, label=""):
    rules = required | optional
    problems = [f"{label}missing field '{name}'" for name in required if name not in data]
    for name, value in data.items():
        if name not in rules:
            problems.append(f"{label}unknown field '{name}'")
            continue
        is_valid, expectation = rules[name]
        if not is_valid(value):
            problems.append(f"{label}'{name}' must be {expectation}, got {value!r}")
    return problems


def _is_text(value):
    return isinstance(value, str) and bool(value.strip())


def _is_sha(value):
    return isinstance(value, str) and bool(_SHA.fullmatch(value))


def _is_integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_count(value):
    return _is_integer(value) and value >= 0


def _is_line_number(value):
    return _is_integer(value) and value >= 1


def _is_boolean(value):
    return isinstance(value, bool)


def _is_list_of_tables(value):
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


_CASE_FIELDS = {
    "pull_request": (_is_text, "a non-empty string"),
    "description": (_is_text, "a non-empty string"),
    "base": (_is_sha, "a full commit SHA"),
    "head": (_is_sha, "a full commit SHA"),
    "max_findings": (_is_count, "a non-negative integer"),
}
_OPTIONAL_CASE_FIELDS = {
    "forbidden_remarks": (_is_list_of_tables, "an array of tables"),
    "expected_defects": (_is_list_of_tables, "an array of tables"),
}
_REMARK_FIELDS = {
    "path": (_is_text, "a non-empty string"),
    "line": (_is_line_number, "a line number"),
    "concept": (_is_text, "a non-empty string"),
}
_DEFECT_FIELDS = {
    **_REMARK_FIELDS,
    "fix": (_is_text, "a non-empty string"),
    "escaped_review": (_is_boolean, "true or false"),
}
_TABLES = (
    ("forbidden_remarks", "forbidden remark", _REMARK_FIELDS),
    ("expected_defects", "expected defect", _DEFECT_FIELDS),
)
