from dataclasses import replace

import pytest

from relecteur.cases import Case, ExpectedDefect, Location
from relecteur.review import Finding, Review
from relecteur.scorer import (
    DefectFinder,
    DefectResult,
    JudgeUnavailable,
    Outcome,
    evaluate,
    score,
)


class FixedJudge:
    """Gives the same probability to every question, and remembers the questions."""

    def __init__(self, answer):
        self.answer = answer
        self.questions = []

    def probability(self, finding, defect):
        self.questions.append((finding, defect))
        return self.answer


CONFIRMING = DefectFinder(FixedJudge(1.0))

APPROVED_PULL_REQUEST = Case(
    name="pr-1-approved-without-comment",
    pull_request="https://forge.example/team/app/pull/1",
    notes="Approved without a single comment: the reviewer should stay silent.",
    base="1" * 40,
    head="2" * 40,
    max_findings=0,
)


def test_a_silence_case_passes_when_the_reviewer_stays_silent():
    result = score(APPROVED_PULL_REQUEST, Review(findings=()), CONFIRMING)

    assert result.outcome is Outcome.PASSED


def finding(path="src/billing.py", line=10, text="A remark."):
    return Finding(path=path, start_line=line, end_line=line, text=text)


def test_a_silence_case_fails_as_soon_as_the_findings_exceed_its_ceiling():
    result = score(APPROVED_PULL_REQUEST, Review(findings=(finding(),)), CONFIRMING)

    assert result.outcome is Outcome.FAILED
    assert result.reasons == ("1 finding(s), ceiling is 0",)


def test_a_silence_case_passes_with_as_many_findings_as_its_ceiling():
    tolerating_two_findings = replace(APPROVED_PULL_REQUEST, max_findings=2)

    result = score(
        tolerating_two_findings, Review(findings=(finding(line=1), finding(line=2))), CONFIRMING
    )

    assert result.outcome is Outcome.PASSED


def test_an_unavailable_model_is_an_error_and_not_a_verdict():
    review = Review(error="model unavailable: rate_limited (HTTP 429)")

    result = score(APPROVED_PULL_REQUEST, review, CONFIRMING)

    assert result.outcome is Outcome.ERROR
    assert result.reasons == ("model unavailable: rate_limited (HTTP 429)",)


UNAVAILABLE = Review(error="model unavailable: overloaded (HTTP 503)")
ANOTHER_APPROVED_PULL_REQUEST = replace(APPROVED_PULL_REQUEST, name="pr-3-approved-without-comment")


def test_a_reviewer_that_did_not_finish_its_review_fails_the_case():
    review = Review(unfinished="review not finished (2 of 2 file(s) not reviewed): budget")

    result = score(APPROVED_PULL_REQUEST, review, CONFIRMING)

    assert result.outcome is Outcome.FAILED
    assert result.reasons == ("review not finished (2 of 2 file(s) not reviewed): budget",)


def test_an_error_without_any_failure_makes_the_verdict_an_error_and_not_a_pass():
    reviews = {APPROVED_PULL_REQUEST: Review(), ANOTHER_APPROVED_PULL_REQUEST: UNAVAILABLE}

    report = evaluate([APPROVED_PULL_REQUEST, ANOTHER_APPROVED_PULL_REQUEST], reviews, CONFIRMING)

    assert report.outcome is Outcome.ERROR


def test_a_failed_case_fails_the_verdict_even_when_another_case_errored():
    reviews = {
        APPROVED_PULL_REQUEST: Review(findings=(finding(),)),
        ANOTHER_APPROVED_PULL_REQUEST: UNAVAILABLE,
    }

    report = evaluate([APPROVED_PULL_REQUEST, ANOTHER_APPROVED_PULL_REQUEST], reviews, CONFIRMING)

    assert report.outcome is Outcome.FAILED


DISCOUNT_APPLIED_TWICE = ExpectedDefect(
    path="src/billing.py",
    lines=(42,),
    concept="Applies the discount a second time when the invoice total is recomputed.",
    fix="https://forge.example/team/app/pull/5",
    escaped_review=True,
)
FIXED_AFTER_APPROVAL = replace(
    APPROVED_PULL_REQUEST,
    name="pr-4-fixed-after-approval",
    max_findings=2,
    expected_defects=(DISCOUNT_APPLIED_TWICE,),
)


def test_a_defect_is_found_when_the_judge_confirms_a_finding_at_its_line():
    remark = finding(line=42, text="The discount is applied again on every recomputation.")

    result = score(FIXED_AFTER_APPROVAL, Review(findings=(remark,)), DefectFinder(FixedJudge(0.9)))

    assert result.outcome is Outcome.PASSED
    assert result.defects == (
        DefectResult(DISCOUNT_APPLIED_TWICE, found=True, finding=remark, probability=0.9),
    )


def test_a_defect_is_missed_when_the_judge_rejects_the_finding_at_its_line():
    remark = finding(line=42, text="Rename `total` to `amount`.")

    result = score(FIXED_AFTER_APPROVAL, Review(findings=(remark,)), DefectFinder(FixedJudge(0.1)))

    assert result.outcome is Outcome.FAILED
    assert result.reasons == (
        "defect missed at src/billing.py:42: "
        "Applies the discount a second time when the invoice total is recomputed.",
    )


def test_the_judge_is_never_asked_about_findings_in_another_file_or_far_from_the_line():
    judge = FixedJudge(1.0)
    elsewhere = (finding(path="src/invoice.py", line=42), finding(path="src/billing.py", line=10))

    result = score(FIXED_AFTER_APPROVAL, Review(findings=elsewhere), DefectFinder(judge))

    assert result.outcome is Outcome.FAILED
    assert judge.questions == []


@pytest.mark.parametrize(
    ("start_line", "end_line", "found"),
    [
        (45, 45, True),
        (39, 39, True),
        (46, 50, False),
        (30, 38, False),
        (30, 50, True),
    ],
    ids=[
        "tolerance below",
        "tolerance above",
        "one line past the tolerance below",
        "one line past the tolerance above",
        "range covering the line",
    ],
)
def test_a_finding_is_judged_only_within_the_line_tolerance(start_line, end_line, found):
    remark = Finding("src/billing.py", start_line, end_line, "The discount is applied twice.")
    within_three_lines = DefectFinder(FixedJudge(1.0), line_tolerance=3)

    result = score(FIXED_AFTER_APPROVAL, Review(findings=(remark,)), within_three_lines)

    assert result.defects[0].found is found


@pytest.mark.parametrize(
    ("line", "asked"), [(25, True), (34, True), (10, False)], ids=["first", "second", "neither"]
)
def test_a_defect_spread_over_several_lines_is_judged_near_any_of_them(line, asked):
    judge = FixedJudge(1.0)
    double_lookup = replace(DISCOUNT_APPLIED_TWICE, lines=(28, 35))
    case = replace(FIXED_AFTER_APPROVAL, expected_defects=(double_lookup,))

    score(case, Review(findings=(finding(line=line),)), DefectFinder(judge))

    assert bool(judge.questions) is asked


@pytest.mark.parametrize(
    ("path", "line", "asked"),
    [("src/invoice.py", 8, True), ("src/invoice.py", 30, False), ("src/billing.py", 40, True)],
    ids=["near the other location", "far from it", "near the first location"],
)
def test_a_defect_that_also_shows_in_another_file_is_judged_near_either_of_them(path, line, asked):
    judge = FixedJudge(1.0)
    also_in_the_invoice = replace(
        DISCOUNT_APPLIED_TWICE, also_at=(Location(path="src/invoice.py", lines=(7,)),)
    )
    case = replace(FIXED_AFTER_APPROVAL, expected_defects=(also_in_the_invoice,))

    score(case, Review(findings=(finding(path=path, line=line),)), DefectFinder(judge))

    assert bool(judge.questions) is asked


def test_without_tolerance_a_finding_must_cover_the_line_of_the_defect():
    exact = DefectFinder(FixedJudge(1.0), line_tolerance=0)
    review = Review(findings=(finding(line=43),))

    result = score(FIXED_AFTER_APPROVAL, review, exact)

    assert result.outcome is Outcome.FAILED


@pytest.mark.parametrize(
    ("probability", "found"), [(0.8, True), (0.79, False)], ids=["at the threshold", "below it"]
)
def test_the_judge_confirms_a_defect_from_the_threshold_on(probability, found):
    demanding = DefectFinder(FixedJudge(probability), threshold=0.8)

    result = score(FIXED_AFTER_APPROVAL, Review(findings=(finding(line=42),)), demanding)

    assert result.defects[0].found is found


class JudgeOfEachDefect:
    """Gives each expected defect its own probability, whatever the finding."""

    def __init__(self, answers):
        self.answers = answers

    def probability(self, finding, defect):
        return self.answers[defect.concept]


def test_a_finding_describing_two_expected_defects_finds_the_likelier_one_only():
    sent_twice = replace(
        DISCOUNT_APPLIED_TWICE,
        lines=(45,),
        concept="Sends the invoice twice when it is recomputed.",
    )
    case = replace(FIXED_AFTER_APPROVAL, expected_defects=(DISCOUNT_APPLIED_TWICE, sent_twice))
    judge = JudgeOfEachDefect({DISCOUNT_APPLIED_TWICE.concept: 1.0, sent_twice.concept: 0.82})
    remark = finding(line=43, text="The discount is applied again on every recomputation.")

    result = score(case, Review(findings=(remark,)), DefectFinder(judge))

    assert [defect_result.found for defect_result in result.defects] == [True, False]


class UnavailableJudge:
    def probability(self, finding, defect):
        raise JudgeUnavailable("judge unavailable: overloaded (HTTP 503)")


def test_an_unavailable_judge_is_an_error_and_not_a_verdict():
    review = Review(findings=(finding(line=42),))

    result = score(FIXED_AFTER_APPROVAL, review, DefectFinder(UnavailableJudge()))

    assert result.outcome is Outcome.ERROR
    assert result.reasons == ("judge unavailable: overloaded (HTTP 503)",)


@pytest.mark.parametrize(
    ("defect_review", "defect_outcome"),
    [(Review(), Outcome.FAILED), (UNAVAILABLE, Outcome.ERROR)],
    ids=["missed defect", "unavailable model"],
)
def test_a_defect_case_is_reported_without_deciding_the_verdict(defect_review, defect_outcome):
    reviews = {APPROVED_PULL_REQUEST: Review(), FIXED_AFTER_APPROVAL: defect_review}

    report = evaluate([APPROVED_PULL_REQUEST, FIXED_AFTER_APPROVAL], reviews, CONFIRMING)

    assert report.results[1].outcome is defect_outcome
    assert report.outcome is Outcome.PASSED


def test_the_defects_of_a_review_the_reviewer_did_not_finish_count_as_missed():
    review = Review(unfinished="review not finished (1 of 1 file(s) not reviewed): budget")

    result = score(FIXED_AFTER_APPROVAL, review, CONFIRMING)

    assert result.outcome is Outcome.FAILED
    assert result.defects == (DefectResult(DISCOUNT_APPLIED_TWICE, found=False),)
