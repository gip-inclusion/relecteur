import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    """A reviewer remark, in the same shape whatever engine produced it.

    `category` (bug, security, maintainability…) and `severity` are the engine's own labels, when
    it gives them.
    """

    path: str
    start_line: int
    end_line: int
    text: str
    category: str | None = None
    severity: str | None = None


@dataclass(frozen=True)
class Review:
    """What the reviewer said on a pull request.

    `error` tells why the model or the engine could not review it: that is no verdict on the
    reviewer. `unfinished` tells why the reviewer, once reached, did not finish its review.
    `tokens` and `seconds` tell what reviewing cost, when known: the tokens the model consumed,
    and the time the review took.
    """

    findings: tuple[Finding, ...] = ()
    error: str | None = None
    unfinished: str | None = None
    tokens: int | None = None
    seconds: float | None = None


def save(review: Review, path: Path) -> None:
    """Writes a review to a JSON file, for it to be scored again without reviewing anew."""
    path.write_text(json.dumps(asdict(review), indent=2, ensure_ascii=False) + "\n", "utf-8")


def load(path: Path) -> Review:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Review(**{**data, "findings": tuple(Finding(**item) for item in data["findings"])})
