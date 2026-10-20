"""The summary a review in CI posts on the pull request, in French, for the team that reads it."""

from relecteur.review import PullRequestReview, Status

_REVIEW_AGAIN = "Pour relancer la review, écrire `@relecteur` dans un commentaire."
_NOT_THE_PR = (
    "Le problème vient du reviewer et non de cette PR : le job de review échoue pour qu'il soit "
    "corrigé."
)


def text(review: PullRequestReview) -> str:
    """What the review came to: the findings it published and where, the files it left unreviewed
    and why, and whether the fault is the model's, out of reach for a while, or the reviewer's."""
    if review.status is Status.NOTHING_TO_REVIEW:
        return (
            "➖ **relecteur** n'a rien relu : aucun des fichiers modifiés par cette PR n'entre "
            "dans le périmètre de la review."
        )
    if review.status is Status.UNAVAILABLE:
        unavailable = f"le modèle était indisponible (`{review.cause}`)."
        reviewed = review.files - review.unreviewed
        if not reviewed:
            return (
                f"⚠️ **relecteur** n'a pu relire aucun fichier de cette PR : {unavailable} "
                f"{_REVIEW_AGAIN}"
            )
        return (
            f"⚠️ **relecteur** n'a relu {_only_files(reviewed)} sur {review.files} : {unavailable} "
            f"{_found_in_part(len(review.findings))} {_REVIEW_AGAIN}"
        )
    if review.status is Status.OVER_BUDGET:
        return (
            f"⚠️ **relecteur** n'a relu {_only_files(review.files - review.unreviewed)} sur "
            f"{review.files} : la review a atteint son plafond de tokens. "
            f"{_found_in_part(len(review.findings))}"
        )
    if review.status is Status.FAILED:
        if not review.files:
            return f"❌ **relecteur** n'a pas pu relire cette PR (`{review.cause}`). {_NOT_THE_PR}"
        unreviewed = (
            f"{_files(review.unreviewed)} sur {review.files} "
            f"{_plural(review.unreviewed, 'non relu')} (`{review.cause}`)."
        )
        found = f" {_found_in_part(len(review.findings))}" if review.findings else ""
        return f"❌ **relecteur** n'a pas terminé sa review : {unreviewed}{found} {_NOT_THE_PR}"
    if not review.findings:
        return "✅ **relecteur** a relu cette PR : rien à signaler."
    return f"🔍 **relecteur** a relu cette PR : {_findings(len(review.findings))}"


def _findings(count):
    if count == 1:
        return "1 remarque, en commentaire sur la ligne concernée."
    return f"{count} remarques, en commentaire sur les lignes concernées."


def _found_in_part(count):
    if not count:
        return "Rien à signaler dans la partie relue."
    if count == 1:
        return "Sa remarque, en commentaire sur la ligne concernée, porte sur la partie relue."
    return (
        f"Ses {count} remarques, en commentaire sur les lignes concernées, portent sur la partie "
        "relue."
    )


def _only_files(count):
    return "qu'un fichier" if count == 1 else f"que {_files(count)}"


def _files(count):
    return f"{count} {_plural(count, 'fichier')}"


def _plural(count, words):
    return f"{words}s" if count > 1 else words
