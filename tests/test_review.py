from relecteur.review import Finding, Review, load, save


def test_a_saved_review_is_read_back_as_it_was(tmp_path):
    review = Review(
        findings=(
            Finding(
                path="app/models/user.rb",
                start_line=84,
                end_line=86,
                text="« archived? » renvoie vrai pour un usager jamais archivé.",
            ),
        ),
        tokens=291_000,
        seconds=1064.2,
    )
    path = tmp_path / "3273.json"

    save(review, path)

    assert load(path) == review


def test_a_saved_review_keeps_why_it_failed(tmp_path):
    review = Review(unfinished="review not finished (1 of 3 file(s) not reviewed): tool_rounds")
    path = tmp_path / "3273.json"

    save(review, path)

    assert load(path) == review
