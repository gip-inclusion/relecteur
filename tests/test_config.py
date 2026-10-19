import pytest

from relecteur import config
from relecteur.open_code_review import Settings


def test_the_settings_of_the_configuration_file_override_the_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        'effort = "medium"\nlanguage = "French"\n'
        'include = ["**/*_spec.rb"]\nexclude = ["db/schema.rb", "db/migrate/**"]\n\n'
        '[model]\nurl = "https://api.anthropic.com"\nname = "claude-opus-5-5"\n\n'
        '[judge]\nname = "jev"\nthreshold = 0.7\n'
    )

    assert config.load(path) == config.Config(
        engine=Settings(
            effort="medium",
            language="French",
            include=["**/*_spec.rb"],
            exclude=["db/schema.rb", "db/migrate/**"],
        ),
        model=config.ModelSettings(url="https://api.anthropic.com", name="claude-opus-5-5"),
        judge=config.JudgeSettings(name="jev", threshold=0.7),
    )


def test_without_a_configuration_file_the_configuration_is_the_defaults(tmp_path):
    assert config.load(tmp_path / "config.toml") == config.Config()


@pytest.mark.parametrize(
    ("content", "problem"),
    [
        ('efort = "medium"', "unknown setting 'efort'"),
        ('effort = "maximum"', "'effort' must be one of low, medium, high, got 'maximum'"),
        ("max_tokens_budget = -1", "'max_tokens_budget' must be a positive integer, got -1"),
        ('include = "**/*.erb"', "'include' must be a list of file patterns, got '**/*.erb'"),
        ('exclude = ["db/**", ""]', "'exclude' must be a list of file patterns, got ['db/**', '']"),
        ('model = "claude-opus-5-5"', "'model' must be a table, got 'claude-opus-5-5'"),
        ('[model]\nnmae = "claude-opus-5-5"', "unknown setting 'model.nmae'"),
        (
            '[model]\nurl = "api.anthropic.com"',
            "'model.url' must be an http or https URL, got 'api.anthropic.com'",
        ),
        (
            '[model]\nprotocol = "grpc"',
            "'model.protocol' must be one of openai, anthropic, got 'grpc'",
        ),
        ('[judge]\nname = "gpt"', "'judge.name' must be one of albert, jev, got 'gpt'"),
        (
            "[judge]\nthreshold = 2",
            "'judge.threshold' must be a probability between 0 and 1, got 2",
        ),
    ],
)
def test_a_wrong_setting_is_refused_with_its_file_and_problem(tmp_path, content, problem):
    path = tmp_path / "config.toml"
    path.write_text(content)

    with pytest.raises(config.InvalidConfig) as error:
        config.load(path)

    assert str(error.value) == f"{path}: {problem}"
