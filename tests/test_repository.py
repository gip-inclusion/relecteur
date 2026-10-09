import pytest

from relecteur import repository


def test_a_variable_of_the_repository_dotenv_file_completes_the_environment(tmp_path):
    (tmp_path / ".env").write_text('RELECTEUR_API_KEY="from-the-file"\nRAILS_ENV=development\n')

    environment = repository.environment(tmp_path, {"HOME": "/home/agent"})

    assert environment["RELECTEUR_API_KEY"] == "from-the-file"
    assert environment["HOME"] == "/home/agent"


def test_the_environment_wins_over_the_repository_dotenv_file(tmp_path):
    (tmp_path / ".env").write_text("RELECTEUR_API_KEY=from-the-file\n")

    environment = repository.environment(tmp_path, {"RELECTEUR_API_KEY": "from-the-shell"})

    assert environment["RELECTEUR_API_KEY"] == "from-the-shell"


def test_without_a_dotenv_file_the_environment_is_left_as_it_is(tmp_path):
    assert repository.environment(tmp_path, {"HOME": "/home/agent"}) == {"HOME": "/home/agent"}


@pytest.mark.parametrize(
    ("files", "instructions"),
    [
        (
            {"REVIEW.md": "Report defects only.\n", "AGENTS.md": "Partials take locals.\n"},
            "Report defects only.\n\nPartials take locals.",
        ),
        ({"REVIEW.md": "Report defects only.\n"}, "Report defects only."),
        ({"AGENTS.md": "Partials take locals.\n"}, "Partials take locals."),
    ],
)
def test_the_reviewer_follows_review_md_then_agents_md_as_far_as_they_exist(
    tmp_path, files, instructions
):
    for name, text in files.items():
        (tmp_path / name).write_text(text)

    assert repository.reviewer_instructions(tmp_path) == instructions


def test_without_review_md_nor_agents_md_the_reviewer_has_no_instructions(tmp_path):
    assert repository.reviewer_instructions(tmp_path) is None
