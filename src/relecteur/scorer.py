"""Scores what the reviewer said against what each case expects.

Pure: the reviews are given, never fetched, and the judge of expected defects is injected, so
scoring itself reaches no network, repository or model.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from relecteur.cases import Case, ExpectedDefect
from relecteur.review import Finding, Review


class Judge(Protocol):
    def probability(self, finding: Finding, defect: ExpectedDefect) -> float:
        """The probability that the finding points out the expected defect."""
        ...


class JudgeUnavailable(Exception):
    """Raised by a judge that could not answer: that is no verdict on the reviewer."""


DEFAULT_LINE_TOLERANCE = 5
DEFAULT_THRESHOLD = 0.5


class Outcome(Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


@dataclass(frozen=True)
class DefectResult:
    """An expected defect, and the finding the judge found the most likely to describe it."""

    defect: ExpectedDefect
    found: bool
    finding: Finding | None = None
    probability: float | None = None


@dataclass(frozen=True)
class DefectFinder:
    """Finds, among the findings of a review, those that point out the expected defects.

    A finding within `line_tolerance` lines of one of a defect's lines, in its file or in one of
    the other files where it shows, is asked to the judge; any other finding never is. A defect is
    found from a probability of `threshold` on, and a finding finds one defect at most: the one
    the judge is the most confident it describes.
    """

    judge: Judge
    line_tolerance: int = DEFAULT_LINE_TOLERANCE
    threshold: float = DEFAULT_THRESHOLD

    def results(
        self, defects: Sequence[ExpectedDefect], findings: Sequence[Finding]
    ) -> tuple[DefectResult, ...]:
        answers = [
            (self.judge.probability(finding, defect), index, finding, defect)
            for index, finding in enumerate(findings)
            for defect in defects
            if self._near(finding, defect)
        ]
        found: dict[ExpectedDefect, DefectResult] = {}
        used = set()
        for probability, index, finding, defect in sorted(answers, key=lambda a: -a[0]):
            if probability >= self.threshold and defect not in found and index not in used:
                found[defect] = DefectResult(defect, True, finding, probability)
                used.add(index)
        return tuple(found.get(defect) or self._missed(defect, answers) for defect in defects)

    def _missed(self, defect, answers):
        """A defect no finding was confirmed for, with the finding the judge rated highest."""
        rated = [(probability, finding) for probability, _, finding, d in answers if d == defect]
        if not rated:
            return DefectResult(defect, found=False)
        probability, finding = max(rated, key=lambda answer: answer[0])
        return DefectResult(defect, False, finding, probability)

    def _near(self, finding, defect):
        first = finding.start_line - self.line_tolerance
        last = finding.end_line + self.line_tolerance
        return any(
            finding.path == location.path and any(first <= line <= last for line in location.lines)
            for location in defect.locations
        )


@dataclass(frozen=True)
class CaseResult:
    case: Case
    outcome: Outcome
    findings: tuple[Finding, ...] = ()
    reasons: tuple[str, ...] = ()
    defects: tuple[DefectResult, ...] = ()


@dataclass(frozen=True)
class Report:
    results: tuple[CaseResult, ...]
    outcome: Outcome


def evaluate(cases: Sequence[Case], reviews: Mapping[Case, Review], finder: DefectFinder) -> Report:
    """Scores every case; only silence cases decide the verdict, defect cases are reported."""
    results = tuple(score(case, reviews[case], finder) for case in cases)
    return Report(
        results, _verdict(result for result in results if not result.case.expected_defects)
    )


def score(case: Case, review: Review, finder: DefectFinder) -> CaseResult:
    if review.error:
        return CaseResult(case, Outcome.ERROR, reasons=(review.error,))
    if review.unfinished:
        missed = tuple(DefectResult(defect, found=False) for defect in case.expected_defects)
        return CaseResult(case, Outcome.FAILED, reasons=(review.unfinished,), defects=missed)
    reasons = []
    if len(review.findings) > case.max_findings:
        reasons.append(f"{len(review.findings)} finding(s), ceiling is {case.max_findings}")
    try:
        defects = finder.results(case.expected_defects, review.findings)
    except JudgeUnavailable as error:
        return CaseResult(case, Outcome.ERROR, review.findings, (str(error),))
    reasons += [
        f"defect missed at {result.defect.location}: {result.defect.concept}"
        for result in defects
        if not result.found
    ]
    return CaseResult(
        case,
        Outcome.FAILED if reasons else Outcome.PASSED,
        review.findings,
        tuple(reasons),
        defects,
    )


def _verdict(results):
    outcomes = {result.outcome for result in results}
    if Outcome.FAILED in outcomes:
        return Outcome.FAILED
    if Outcome.ERROR in outcomes:
        return Outcome.ERROR
    return Outcome.PASSED
