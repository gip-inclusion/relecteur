import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_SHA = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class Location:
    path: str
    lines: tuple[int, ...]

    def __str__(self) -> str:
        return f"{self.path}:{','.join(str(line) for line in self.lines)}"


@dataclass(frozen=True)
class ExpectedDefect:
    """A defect the pull request introduced, which the change linked by `fix` corrected afterwards.

    `lines` of `path` are where a reviewer may point it out, and `also_at` other files where it
    shows, such as a caller the change breaks. `escaped_review` tells whether the human review of
    the pull request let it through.
    """

    path: str
    lines: tuple[int, ...]
    concept: str
    fix: str
    escaped_review: bool
    also_at: tuple[Location, ...] = ()

    @property
    def locations(self) -> tuple[Location, ...]:
        return (Location(self.path, self.lines), *self.also_at)

    @property
    def location(self) -> str:
        return ", ".join(str(location) for location in self.locations)


@dataclass(frozen=True)
class PullRequestText:
    """The title and description of a pull request, as its author wrote them."""

    title: str
    description: str | None = None

    @property
    def text(self) -> str:
        """What the reviewer reads as the author's intent: the title, then the description."""
        return f"{self.title}\n\n{self.description}" if self.description else self.title


@dataclass(frozen=True)
class Case:
    """A past pull request, frozen by its base and head commits, and what the reviewer should do.

    `notes` tell the humans reading the case why it expects what it does; the reviewer never reads
    them. It reads `pr`, the text of the pull request, as the author's intent.
    """

    name: str
    pull_request: str
    notes: str
    base: str
    head: str
    max_findings: int
    expected_defects: tuple[ExpectedDefect, ...] = ()
    pr: PullRequestText | None = None


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
        notes=data["notes"],
        base=data["base"],
        head=data["head"],
        max_findings=data["max_findings"],
        expected_defects=tuple(
            _expected_defect(**defect) for defect in data.get("expected_defects", [])
        ),
        pr=_pull_request_text(**data["pr"]) if "pr" in data else None,
    )


def _pull_request_text(title, description=None):
    return PullRequestText(title.strip(), description.strip() if description else None)


def _expected_defect(line, also_at=(), **fields):
    return ExpectedDefect(
        lines=_lines(line),
        also_at=tuple(Location(other["path"], _lines(other["line"])) for other in also_at),
        **fields,
    )


def _lines(line):
    return tuple(line) if isinstance(line, list) else (line,)


def _case_problems(data):
    problems = _problems(data, _CASE_FIELDS, _OPTIONAL_CASE_FIELDS)
    defects = data.get("expected_defects", [])
    if _is_list_of_tables(defects):
        for number, defect in enumerate(defects, start=1):
            label = f"expected defect {number}: "
            problems += _problems(defect, _DEFECT_FIELDS, _OPTIONAL_DEFECT_FIELDS, label=label)
            others = defect.get("also_at", [])
            if _is_list_of_tables(others):
                for other_number, other in enumerate(others, start=1):
                    problems += _problems(
                        other, _LOCATION_FIELDS, {}, label=f"{label}other location {other_number}: "
                    )
    if isinstance(pr := data.get("pr"), dict):
        problems += _problems(pr, _PR_FIELDS, _OPTIONAL_PR_FIELDS, label="pr: ")
    ceiling = data.get("max_findings")
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


def _is_line_or_lines(value):
    if isinstance(value, list):
        return bool(value) and all(_is_line_number(line) for line in value)
    return _is_line_number(value)


def _is_boolean(value):
    return isinstance(value, bool)


def _is_table(value):
    return isinstance(value, dict)


def _is_list_of_tables(value):
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


_CASE_FIELDS = {
    "pull_request": (_is_text, "a non-empty string"),
    "notes": (_is_text, "a non-empty string"),
    "base": (_is_sha, "a full commit SHA"),
    "head": (_is_sha, "a full commit SHA"),
    "max_findings": (_is_count, "a non-negative integer"),
}
_OPTIONAL_CASE_FIELDS = {
    "pr": (_is_table, "a table"),
    "expected_defects": (_is_list_of_tables, "an array of tables"),
}
_PR_FIELDS = {"title": (_is_text, "a non-empty string")}
_OPTIONAL_PR_FIELDS = {"description": (_is_text, "a non-empty string")}
_LOCATION_FIELDS = {
    "path": (_is_text, "a non-empty string"),
    "line": (_is_line_or_lines, "a line number or a non-empty list of line numbers"),
}
_DEFECT_FIELDS = {
    **_LOCATION_FIELDS,
    "concept": (_is_text, "a non-empty string"),
    "fix": (_is_text, "a non-empty string"),
    "escaped_review": (_is_boolean, "true or false"),
}
_OPTIONAL_DEFECT_FIELDS = {"also_at": (_is_list_of_tables, "an array of tables")}
