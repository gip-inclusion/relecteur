"""The repository's `.relecteur/config.toml`: the engine and the model that review, and the judge.

The file holds no secret: the reviewer's and the judge's API keys come from the environment.
"""

import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from relecteur import judges
from relecteur.model import DEFAULT_NAME, DEFAULT_URL, PROTOCOLS
from relecteur.open_code_review import EFFORTS, Settings
from relecteur.scorer import DEFAULT_THRESHOLD


@dataclass(frozen=True)
class ModelSettings:
    """The model that reviews, and its endpoint, whose protocol the URL tells unless given."""

    url: str = DEFAULT_URL
    name: str = DEFAULT_NAME
    protocol: str | None = None


@dataclass(frozen=True)
class JudgeSettings:
    """The judge of expected defects, its model (the judge's default without one), and the
    probability from which it confirms a defect."""

    name: str = "albert"
    model: str | None = None
    threshold: float = DEFAULT_THRESHOLD


@dataclass(frozen=True)
class Config:
    engine: Settings = field(default_factory=Settings)
    model: ModelSettings = field(default_factory=ModelSettings)
    judge: JudgeSettings = field(default_factory=JudgeSettings)


class InvalidConfig(Exception):
    pass


def load(path: Path) -> Config:
    """The configuration of a TOML file, the defaults standing for what it leaves out.

    The engine settings sit at the top of the file, the model's in a `[model]` table and the
    judge's in a `[judge]` table. Without such a file, the configuration is all the defaults.
    """
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Config()
    except tomllib.TOMLDecodeError as error:
        raise InvalidConfig(f"{path}: not valid TOML: {error}") from error
    tables = {name: data.pop(name, {}) for name in ("model", "judge")}
    for name, table in tables.items():
        if not isinstance(table, dict):
            raise InvalidConfig(f"{path}: '{name}' must be a table, got {table!r}")
    return Config(
        engine=Settings(**_checked(path, data, _ENGINE)),
        model=ModelSettings(**_checked(path, tables["model"], _MODEL, "model.")),
        judge=JudgeSettings(**_checked(path, tables["judge"], _JUDGE, "judge.")),
    )


def _checked(
    path: Path,
    data: dict[str, Any],
    settings: Mapping[str, tuple[Callable[[Any], bool], str]],
    prefix: str = "",
) -> dict[str, Any]:
    for name, value in data.items():
        if name not in settings:
            raise InvalidConfig(f"{path}: unknown setting '{prefix}{name}'")
        is_valid, expectation = settings[name]
        if not is_valid(value):
            raise InvalidConfig(f"{path}: '{prefix}{name}' must be {expectation}, got {value!r}")
    return data


def _is_positive(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_text(value):
    return isinstance(value, str) and bool(value.strip())


def _is_url(value):
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _is_probability(value):
    return isinstance(value, int | float) and not isinstance(value, bool) and 0 <= value <= 1


_ENGINE = {
    "effort": (lambda value: value in EFFORTS, f"one of {', '.join(EFFORTS)}"),
    "concurrency": (_is_positive, "a positive integer"),
    "max_tokens_budget": (_is_positive, "a positive integer"),
    "language": (_is_text, "a non-empty string"),
}
_MODEL = {
    "url": (_is_url, "an http or https URL"),
    "name": (_is_text, "a non-empty string"),
    "protocol": (lambda value: value in PROTOCOLS, f"one of {', '.join(PROTOCOLS)}"),
}
_JUDGE = {
    "name": (
        lambda value: value in judges.DEFAULT_MODELS,
        f"one of {', '.join(sorted(judges.DEFAULT_MODELS))}",
    ),
    "model": (_is_text, "a non-empty string"),
    "threshold": (_is_probability, "a probability between 0 and 1"),
}
