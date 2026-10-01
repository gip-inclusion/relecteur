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
    """What the reviewer said on a pull request.

    `error` tells why the model or the engine could not review it: that is no verdict on the
    reviewer. `unfinished` tells why the reviewer, once reached, did not finish its review.
    """

    findings: tuple[Finding, ...] = ()
    error: str | None = None
    unfinished: str | None = None
