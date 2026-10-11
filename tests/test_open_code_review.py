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
                category="maintainability",
                severity="low",
            ),
            Finding(
                path="app/jobs/alert_user_added_to_another_department_job.rb",
                start_line=33,
                end_line=35,
                text=SLACK_REMARK,
                category="maintainability",
                severity="low",
            ),
        ),
        tokens=9690,
    )


def test_a_silent_review_has_no_finding():
    assert parse("silent.json") == Review(tokens=19069)


def test_a_pull_request_without_any_reviewed_file_is_an_error_and_not_a_silence():
    assert parse("no-supported-files.json") == Review(
        error="no file reviewed: the engine supports none of the files this pull request changes"
    )


def test_a_review_cut_short_by_a_rate_limit_is_an_error_without_findings():
    review = parse("rate-limited.json")

    assert review == Review(
        error="model unavailable, review incomplete (3 of 19 file(s) not reviewed): "
        "rate_limited (HTTP 429)",
        tokens=1811059,
    )


def test_an_overloaded_model_on_every_file_is_an_error():
    review = parse("overloaded.json", returncode=1)

    assert review == Review(
        error="model unavailable, review incomplete (1 of 1 file(s) not reviewed): "
        "overloaded (HTTP 503)",
        tokens=0,
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

    assert review == Review(
        unfinished="review not finished (2 of 2 file(s) not reviewed): budget", tokens=273391
    )


def test_a_review_cut_short_by_a_timeout_is_an_error_without_findings():
    review = parse("timed-out.json")

    assert review.error == "review incomplete (6 of 19 file(s) not reviewed): timeout"
    assert review.findings == ()


@pytest.mark.parametrize(
    ("output", "session"),
    [
        ("rate-limited.json", "51bd43a9-3631-4302-9708-1581af54208f"),
        ("timed-out.json", "7e3b9c41-2d6a-4f8e-b5c0-91a4d2e6f310"),
        ("request-timed-out.json", "7e3b9c41-2d6a-4f8e-b5c0-91a4d2e6f310"),
    ],
)
def test_a_review_cut_short_by_a_rate_limit_or_a_timeout_is_resumed_from_its_session(
    output, session
):
    assert open_code_review.session_to_resume((OUTPUTS / output).read_text()) == session


@pytest.mark.parametrize("output", ["silent.json", "overloaded.json", "tool-rounds-exhausted.json"])
def test_a_review_cut_short_by_anything_else_is_not_resumed(output):
    assert open_code_review.session_to_resume((OUTPUTS / output).read_text()) is None


@pytest.mark.parametrize(
    ("output", "tokens"),
    [("silent.json", 19069), ("rate-limited.json", 1811059), ("no-supported-files.json", None)],
)
def test_a_review_tells_the_tokens_the_model_consumed_even_when_cut_short(output, tokens):
    assert parse(output).tokens == tokens


def test_the_settings_of_the_configuration_file_override_the_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('effort = "medium"\nlanguage = "French"\n')

    assert open_code_review.load_settings(path) == open_code_review.Settings(
        effort="medium", language="French"
    )


def test_without_a_configuration_file_the_settings_are_the_defaults(tmp_path):
    assert open_code_review.load_settings(tmp_path / "config.toml") == open_code_review.Settings()


@pytest.mark.parametrize(
    ("content", "problem"),
    [
        ('efort = "medium"', "unknown setting 'efort'"),
        ('effort = "maximum"', "'effort' must be one of low, medium, high, got 'maximum'"),
        ("max_tokens_budget = -1", "'max_tokens_budget' must be a positive integer, got -1"),
    ],
)
def test_a_wrong_setting_is_refused_with_its_file_and_problem(tmp_path, content, problem):
    path = tmp_path / "config.toml"
    path.write_text(content)

    with pytest.raises(open_code_review.InvalidSettings) as error:
        open_code_review.load_settings(path)

    assert str(error.value) == f"{path}: {problem}"
