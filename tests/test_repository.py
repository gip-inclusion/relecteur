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
