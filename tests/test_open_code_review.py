from pathlib import Path

import pytest

from relecteur import open_code_review
from relecteur.review import Finding, Review

OUTPUTS = Path(__file__).parent / "fixtures" / "open_code_review"


def parse(output, returncode=0, stderr=""):
    return open_code_review.parse((OUTPUTS / output).read_text(), stderr, returncode)


SLACK_REMARK = (
    "Consider rescuing potential exceptions from the Slack client to avoid job retries that could "
    "spam Slack and hide failures. Adding a rescue block with logging preserves observability "
    "after removing Sentry."
)


def test_the_engine_comments_become_normalized_findings():
    review = parse("with-comments.json")

    assert review == Review(
        findings=(
            Finding(
                path="app/jobs/alert_motif_category_has_changed_job.rb",
                start_line=21,
                end_line=23,
                text=SLACK_REMARK,
            ),
            Finding(
                path="app/jobs/alert_user_added_to_another_department_job.rb",
                start_line=33,
                end_line=35,
                text=SLACK_REMARK,
            ),
        )
    )


def test_a_silent_review_has_no_finding():
    assert parse("silent.json") == Review()


def test_a_pull_request_without_any_reviewed_file_is_an_error_and_not_a_silence():
    assert parse("no-supported-files.json") == Review(
        error="no file reviewed: the engine supports none of the files this pull request changes"
    )


def test_a_review_cut_short_by_a_rate_limit_is_an_error_without_findings():
    review = parse("rate-limited.json")

    assert review == Review(
        error="model unavailable, review incomplete (3 of 19 file(s) not reviewed): "
        "rate_limited (HTTP 429)"
    )


def test_an_overloaded_model_on_every_file_is_an_error():
    review = parse("overloaded.json", returncode=1)

    assert review == Review(
        error="model unavailable, review incomplete (1 of 1 file(s) not reviewed): "
        "overloaded (HTTP 503)"
    )


def test_an_engine_stopping_without_output_is_an_error_carrying_its_message():
    stderr = (
        "[ocr] loading configuration\n"
        "Error: resolve LLM endpoint: no valid LLM endpoint configured\n"
    )

    review = open_code_review.parse("", stderr, 1)

    assert review == Review(
        error="open-code-review exited with code 1: "
        "Error: resolve LLM endpoint: no valid LLM endpoint configured"
    )


def test_an_output_of_unexpected_shape_is_an_error_and_not_a_crash():
    review = open_code_review.parse('{"status": "complete"}', "", 0)

    assert review.findings == ()
    assert review.error is not None
    assert review.error.startswith("unexpected open-code-review output")


def test_a_real_review_whose_model_never_finished_is_unfinished_and_not_unavailable():
    review = parse("tool-rounds-exhausted.json", returncode=1)

    assert review == Review(unfinished="review not finished (2 of 2 file(s) not reviewed): budget")


def test_a_review_cut_short_by_a_rate_limit_is_resumed_from_its_session():
    output = (OUTPUTS / "rate-limited.json").read_text()

    assert open_code_review.session_to_resume(output) == "51bd43a9-3631-4302-9708-1581af54208f"


@pytest.mark.parametrize("output", ["silent.json", "overloaded.json", "tool-rounds-exhausted.json"])
def test_a_review_cut_short_by_anything_but_a_rate_limit_is_not_resumed(output):
    assert open_code_review.session_to_resume((OUTPUTS / output).read_text()) is None
