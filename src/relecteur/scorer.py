"""Scores what the reviewer said against what each case expects.

Pure: the reviews are given, never fetched, and the judge of expected defects is injected, so
scoring itself reaches no network, repository or model.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from relecteur.cases import Case, ExpectedDefect
from relecteur.review import Finding, Review

Judge = Callable[[Finding, ExpectedDefect], float]
"""Gives the probability that a finding describes an expected defect."""


class JudgeUnavailable(Exception):
    """Raised by a judge that could not answer: that is no verdict on the reviewer."""


DEFAULT_LINE_TOLERANCE = 5
DEFAULT_THRESHOLD = 0.5


@dataclass(frozen=True)
class Matching:
    """How a finding is matched to an expected defect.

    A finding of the defect's file, within `line_tolerance` lines of one of its lines, is asked to
    the judge; any other finding never is. The defect is found from a probability of `threshold`
    on.
    """

    judge: Judge
    line_tolerance: int = DEFAULT_LINE_TOLERANCE
    threshold: float = DEFAULT_THRESHOLD


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


def evaluate(cases: Sequence[Case], reviews: Mapping[Case, Review], matching: Matching) -> Report:
    """Scores every case; only silence cases decide the verdict, defect cases are reported."""
    results = tuple(score(case, reviews[case], matching) for case in cases)
    return Report(
        results, _verdict(result for result in results if not result.case.expected_defects)
    )


def score(case: Case, review: Review, matching: Matching) -> CaseResult:
    if review.error:
        return CaseResult(case, Outcome.ERROR, reasons=(review.error,))
    if review.unfinished:
        missed = tuple(DefectResult(defect, found=False) for defect in case.expected_defects)
        return CaseResult(case, Outcome.FAILED, reasons=(review.unfinished,), defects=missed)
    reasons = []
    if len(review.findings) > case.max_findings:
        reasons.append(f"{len(review.findings)} finding(s), ceiling is {case.max_findings}")
    reasons += [
        f"forbidden remark repeated at {remark.path}:{remark.line}: {remark.concept}"
        for remark in case.forbidden_remarks
        if any(_repeats(finding, remark) for finding in review.findings)
    ]
    try:
        defects = tuple(
            _defect_result(defect, review.findings, matching) for defect in case.expected_defects
        )
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


def _defect_result(defect, findings, matching):
    answers = [
        (matching.judge(finding, defect), finding)
        for finding in findings
        if _near(finding, defect, matching.line_tolerance)
    ]
    if not answers:
        return DefectResult(defect, found=False)
    probability, finding = max(answers, key=lambda answer: answer[0])
    return DefectResult(defect, probability >= matching.threshold, finding, probability)


def _near(finding, defect, tolerance):
    return finding.path == defect.path and any(
        finding.start_line - tolerance <= line <= finding.end_line + tolerance
        for line in defect.lines
    )


def _repeats(finding, remark):
    return finding.path == remark.path and finding.start_line <= remark.line <= finding.end_line


def _verdict(results):
    outcomes = {result.outcome for result in results}
    if Outcome.FAILED in outcomes:
        return Outcome.FAILED
    if Outcome.ERROR in outcomes:
        return Outcome.ERROR
    return Outcome.PASSED
