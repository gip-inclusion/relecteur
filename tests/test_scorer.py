from dataclasses import replace

from relecteur.cases import Case, ForbiddenRemark
from relecteur.review import Finding, Review
from relecteur.scorer import Outcome, evaluate, score

APPROVED_PULL_REQUEST = Case(
    name="pr-1-approved-without-comment",
    pull_request="https://forge.example/team/app/pull/1",
    description="Approved without a single comment: the reviewer should stay silent.",
    base="1" * 40,
    head="2" * 40,
    max_findings=0,
)


def test_a_silence_case_passes_when_the_reviewer_stays_silent():
    result = score(APPROVED_PULL_REQUEST, Review(findings=()))

    assert result.outcome is Outcome.PASSED


def finding(path="src/billing.py", line=10, text="A remark."):
    return Finding(path=path, start_line=line, end_line=line, text=text)


def test_a_silence_case_fails_as_soon_as_the_findings_exceed_its_ceiling():
    result = score(APPROVED_PULL_REQUEST, Review(findings=(finding(),)))

    assert result.outcome is Outcome.FAILED
    assert result.reasons == ("1 finding(s), ceiling is 0",)


def test_a_silence_case_passes_with_as_many_findings_as_its_ceiling():
    tolerating_two_findings = replace(APPROVED_PULL_REQUEST, max_findings=2)

    result = score(tolerating_two_findings, Review(findings=(finding(line=1), finding(line=2))))

    assert result.outcome is Outcome.PASSED


WITH_A_FORBIDDEN_REMARK = replace(
    APPROVED_PULL_REQUEST,
    max_findings=3,
    forbidden_remarks=(
        ForbiddenRemark(
            path="src/billing.py",
            line=42,
            concept="Asks to rename the method although its name matches the domain.",
        ),
    ),
)


def test_a_finding_on_a_forbidden_remark_fails_the_case_even_under_its_ceiling():
    result = score(
        WITH_A_FORBIDDEN_REMARK, Review(findings=(finding(path="src/billing.py", line=42),))
    )

    assert result.outcome is Outcome.FAILED
    assert result.reasons == (
        "forbidden remark repeated at src/billing.py:42: "
        "Asks to rename the method although its name matches the domain.",
    )


def test_a_finding_whose_range_covers_a_forbidden_remark_repeats_it():
    covering = Finding(path="src/billing.py", start_line=40, end_line=45, text="A remark.")

    result = score(WITH_A_FORBIDDEN_REMARK, Review(findings=(covering,)))

    assert result.outcome is Outcome.FAILED


def test_a_finding_elsewhere_than_a_forbidden_remark_does_not_repeat_it():
    elsewhere = (finding(path="src/billing.py", line=43), finding(path="src/invoice.py", line=42))

    result = score(WITH_A_FORBIDDEN_REMARK, Review(findings=elsewhere))

    assert result.outcome is Outcome.PASSED


def test_an_unavailable_model_is_an_error_and_not_a_verdict():
    review = Review(error="model unavailable: rate_limited (HTTP 429)")

    result = score(APPROVED_PULL_REQUEST, review)

    assert result.outcome is Outcome.ERROR
    assert result.reasons == ("model unavailable: rate_limited (HTTP 429)",)


UNAVAILABLE = Review(error="model unavailable: overloaded (HTTP 503)")
ANOTHER_APPROVED_PULL_REQUEST = replace(APPROVED_PULL_REQUEST, name="pr-3-approved-without-comment")


def test_an_error_without_any_failure_makes_the_verdict_an_error_and_not_a_pass():
    reviews = {APPROVED_PULL_REQUEST: Review(), ANOTHER_APPROVED_PULL_REQUEST: UNAVAILABLE}

    report = evaluate([APPROVED_PULL_REQUEST, ANOTHER_APPROVED_PULL_REQUEST], reviews)

    assert report.outcome is Outcome.ERROR


def test_a_failed_case_fails_the_verdict_even_when_another_case_errored():
    reviews = {
        APPROVED_PULL_REQUEST: Review(findings=(finding(),)),
        ANOTHER_APPROVED_PULL_REQUEST: UNAVAILABLE,
    }

    report = evaluate([APPROVED_PULL_REQUEST, ANOTHER_APPROVED_PULL_REQUEST], reviews)

    assert report.outcome is Outcome.FAILED
