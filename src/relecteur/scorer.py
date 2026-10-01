"""Scores what the reviewer said against what each case expects.

Pure: the reviews are given, never fetched, so scoring reaches no network, repository or model.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from relecteur.cases import Case
from relecteur.review import Finding, Review


class Outcome(Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


@dataclass(frozen=True)
class CaseResult:
    case: Case
    outcome: Outcome
    findings: tuple[Finding, ...] = ()
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Report:
    results: tuple[CaseResult, ...]
    outcome: Outcome


def evaluate(cases: Sequence[Case], reviews: Mapping[Case, Review]) -> Report:
    """Scores every case against its review, and gives the verdict of the whole."""
    results = tuple(score(case, reviews[case]) for case in cases)
    return Report(results, _verdict(results))


def score(case: Case, review: Review) -> CaseResult:
    if review.error:
        return CaseResult(case, Outcome.ERROR, reasons=(review.error,))
    reasons = []
    if len(review.findings) > case.max_findings:
        reasons.append(f"{len(review.findings)} finding(s), ceiling is {case.max_findings}")
    reasons += [
        f"forbidden remark repeated at {remark.path}:{remark.line}: {remark.concept}"
        for remark in case.forbidden_remarks
        if any(_repeats(finding, remark) for finding in review.findings)
    ]
    outcome = Outcome.FAILED if reasons else Outcome.PASSED
    return CaseResult(case, outcome, review.findings, tuple(reasons))


def _repeats(finding, remark):
    return finding.path == remark.path and finding.start_line <= remark.line <= finding.end_line


def _verdict(results):
    outcomes = {result.outcome for result in results}
    if Outcome.FAILED in outcomes:
        return Outcome.FAILED
    if Outcome.ERROR in outcomes:
        return Outcome.ERROR
    return Outcome.PASSED
