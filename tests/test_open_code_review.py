from pathlib import Path

from relecteur import open_code_review
from relecteur.review import Finding, Review

OUTPUTS = Path(__file__).parent / "fixtures" / "open_code_review"


def parse(output: str, returncode: int = 0, stderr: str = "") -> Review:
    return open_code_review.parse((OUTPUTS / output).read_text(), stderr, returncode)


def test_the_engine_comments_become_normalized_findings() -> None:
    review = parse("with-comments.json")

    assert review == Review(
        findings=(
            Finding(
                path="src/billing.py",
                start_line=42,
                end_line=42,
                text="`total` est calculé avant l'application de la remise : "
                "le montant facturé ignore la remise.",
            ),
            Finding(
                path="src/invoice.py",
                start_line=17,
                end_line=21,
                text="La requête interpole `customer_id` dans le SQL : risque d'injection.",
            ),
        )
    )


def test_a_silent_review_has_no_finding() -> None:
    assert parse("silent.json") == Review()


def test_a_pull_request_without_any_supported_file_is_a_silent_review() -> None:
    assert parse("no-supported-files.json") == Review()


def test_a_review_cut_short_by_a_rate_limit_is_an_error_without_findings() -> None:
    review = parse("rate-limited.json")

    assert review == Review(
        error="model unavailable, review incomplete (1 of 2 file(s) not reviewed): "
        "rate_limited (HTTP 429)"
    )


def test_an_overloaded_model_on_every_file_is_an_error() -> None:
    review = parse("overloaded.json", returncode=1)

    assert review == Review(
        error="model unavailable, review incomplete (1 of 1 file(s) not reviewed): "
        "overloaded (HTTP 503)"
    )


def test_an_engine_stopping_without_output_is_an_error_carrying_its_message() -> None:
    stderr = (
        "[ocr] loading configuration\n"
        "Error: resolve LLM endpoint: no valid LLM endpoint configured\n"
    )

    review = open_code_review.parse("", stderr, 1)

    assert review == Review(
        error="open-code-review exited with code 1: "
        "Error: resolve LLM endpoint: no valid LLM endpoint configured"
    )


def test_an_output_of_unexpected_shape_is_an_error_and_not_a_crash() -> None:
    review = open_code_review.parse('{"status": "complete"}', "", 0)

    assert review == Review(error="unexpected open-code-review output: KeyError('comments')")
