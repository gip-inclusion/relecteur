from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    """A reviewer remark, in the same shape whatever engine produced it."""

    path: str
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True)
class Review:
    """What the reviewer said on a pull request, or why it could not say anything."""

    findings: tuple[Finding, ...] = ()
    error: str | None = None
