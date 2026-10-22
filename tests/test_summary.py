from pathlib import Path

import pytest

from relecteur import open_code_review, summary
from relecteur.review import Finding, PullRequestReview, Status

OUTPUTS = Path(__file__).parent / "fixtures" / "open_code_review"
FINDING = Finding("app/models/user.rb", 12, 12, "Remarque")


def summarized(output, stderr=""):
    """The summary of a review in CI whose engine wrote `output`, and whether the review failed."""
    review = open_code_review.pull_request_review((OUTPUTS / output).read_text(), stderr)
    return summary.text(review), review.failed


def test_a_complete_review_without_findings_says_the_pull_request_was_reviewed():
    assert summarized("silent.json") == (
        "✅ **relecteur** a relu cette PR : rien à signaler.",
        False,
    )


def test_a_complete_review_with_findings_points_to_them():
    assert summarized("with-comments.json") == (
        "🔍 **relecteur** a relu cette PR : 2 remarques, en commentaire sur les lignes concernées.",
        False,
    )


def test_a_single_finding_is_told_in_the_singular():
    assert summary.text(PullRequestReview(Status.REVIEWED, findings=(FINDING,))) == (
        "🔍 **relecteur** a relu cette PR : 1 remarque, en commentaire sur la ligne concernée."
    )


def test_a_review_cut_short_by_the_model_tells_what_was_left_out_and_how_to_review_again():
    assert summarized("rate-limited.json") == (
        "⚠️ **relecteur** n'a relu que 16 fichiers sur 19 : le modèle était indisponible "
        "(`rate_limited (HTTP 429)`). Ses 9 remarques, en commentaire sur les lignes concernées, "
        "portent sur la partie relue. Pour relancer la review, écrire `@relecteur` dans un "
        "commentaire.",
        False,
    )


def test_a_model_unavailable_for_every_file_is_told_without_failing_the_review():
    assert summarized("overloaded.json") == (
        "⚠️ **relecteur** n'a pu relire aucun fichier de cette PR : le modèle était indisponible "
        "(`provider (HTTP 503)`). Pour relancer la review, écrire `@relecteur` dans un "
        "commentaire.",
        False,
    )


def test_files_left_out_by_timeouts_give_the_timeout_as_cause():
    text, failed = summarized("timed-out.json")

    assert text.startswith(
        "⚠️ **relecteur** n'a relu que 13 fichiers sur 19 : le modèle était indisponible "
        "(`timeout`)."
    )
    assert not failed


def test_a_reviewer_that_did_not_finish_fails_the_review_and_says_the_fault_is_not_the_pr():
    assert summarized("tool-rounds-exhausted.json") == (
        "❌ **relecteur** n'a pas terminé sa review : 2 fichiers sur 2 non relus (`budget`). Le "
        "problème vient du reviewer et non de cette PR : le job de review échoue pour qu'il soit "
        "corrigé.",
        True,
    )


@pytest.mark.parametrize(
    ("output", "cause"),
    [
        ("refused-key.json", "authentication (HTTP 401)"),
        ("unknown-model.json", "provider (HTTP 404)"),
    ],
)
def test_a_refused_request_fails_the_review_rather_than_passing_for_an_unavailable_model(
    output, cause
):
    text, failed = summarized(output)

    assert text.startswith(
        f"❌ **relecteur** n'a pas terminé sa review : 1 fichier sur 1 non relu (`{cause}`)."
    )
    assert failed


def test_a_pull_request_without_any_file_to_review_is_told_so_without_failing():
    assert summarized("no-supported-files.json") == (
        "➖ **relecteur** n'a rien relu : aucun des fichiers modifiés par cette PR n'entre dans "
        "le périmètre de la review.",
        False,
    )


@pytest.mark.parametrize(
    ("stderr", "cause"),
    [
        ("[ocr] loading configuration\nError: llm.url is required\n", "Error: llm.url is required"),
        ("", "no output"),
    ],
)
def test_an_engine_that_wrote_no_review_fails_it_with_its_last_message(stderr, cause):
    review = open_code_review.pull_request_review("", stderr)

    assert summary.text(review) == (
        f"❌ **relecteur** n'a pas pu relire cette PR (`{cause}`). Le problème vient du reviewer "
        "et non de cette PR : le job de review échoue pour qu'il soit corrigé."
    )
    assert review.failed


@pytest.mark.parametrize(
    ("findings", "told"),
    [
        ((), "Rien à signaler dans la partie relue."),
        (
            (FINDING,),
            "Sa remarque, en commentaire sur la ligne concernée, porte sur la partie relue.",
        ),
    ],
)
def test_a_review_cut_short_tells_what_it_found_in_the_part_it_reviewed(findings, told):
    review = PullRequestReview(
        Status.UNAVAILABLE, findings, files=3, unreviewed=2, cause="rate_limited (HTTP 429)"
    )

    assert summary.text(review) == (
        "⚠️ **relecteur** n'a relu qu'un fichier sur 3 : le modèle était indisponible "
        f"(`rate_limited (HTTP 429)`). {told} Pour relancer la review, écrire `@relecteur` dans "
        "un commentaire."
    )


def test_an_unfinished_review_tells_the_findings_it_published_on_the_part_it_reviewed():
    review = PullRequestReview(
        Status.FAILED, findings=(FINDING, FINDING), files=5, unreviewed=1, cause="budget"
    )

    assert summary.text(review) == (
        "❌ **relecteur** n'a pas terminé sa review : 1 fichier sur 5 non relu (`budget`). Ses 2 "
        "remarques, en commentaire sur les lignes concernées, portent sur la partie relue. Le "
        "problème vient du reviewer et non de cette PR : le job de review échoue pour qu'il soit "
        "corrigé."
    )


def test_a_review_that_reached_its_token_budget_tells_what_it_left_out_without_failing():
    assert summarized("token-budget-reached.json") == (
        "⚠️ **relecteur** n'a relu que 16 fichiers sur 19 : la review a atteint son plafond de "
        "tokens. Ses 9 remarques, en commentaire sur les lignes concernées, portent sur la partie "
        "relue.",
        False,
    )


def test_an_output_of_unexpected_shape_fails_the_review_rather_than_passing_for_silence():
    review = open_code_review.pull_request_review('{"status": "complete"}', "")

    assert summary.text(review).startswith(
        "❌ **relecteur** n'a pas pu relire cette PR (`unexpected open-code-review output: "
    )
    assert review.failed


@pytest.mark.parametrize(
    ("review", "status"),
    [
        (PullRequestReview(Status.REVIEWED), ("success", "Rien à signaler")),
        (PullRequestReview(Status.REVIEWED, findings=(FINDING,)), ("success", "1 remarque")),
        (PullRequestReview(Status.REVIEWED, findings=(FINDING,) * 2), ("success", "2 remarques")),
        (PullRequestReview(Status.NOTHING_TO_REVIEW), ("success", "Aucun fichier à relire")),
        (
            PullRequestReview(Status.UNAVAILABLE, files=3, unreviewed=3),
            ("success", "Review incomplète : modèle indisponible"),
        ),
        (
            PullRequestReview(Status.OVER_BUDGET, files=3, unreviewed=1),
            ("success", "Review incomplète : plafond de tokens atteint"),
        ),
        (PullRequestReview(Status.FAILED), ("failure", "Le reviewer n'a pas pu relire la PR")),
    ],
)
def test_the_commit_status_tells_in_short_how_the_review_ended_and_fails_with_the_reviewer_only(
    review, status
):
    assert summary.commit_status(review) == status
