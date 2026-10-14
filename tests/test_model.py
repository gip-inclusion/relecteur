import pytest

from relecteur.model import DEFAULT_NAME, DEFAULT_URL, MissingApiKey, Model

KEYS = {"RELECTEUR_API_KEY": "reviewer-key"}


def test_anthropic_s_api_is_reached_through_its_own_protocol():
    model = Model.reviewer("https://api.anthropic.com", "claude-opus-5-5", None, KEYS)

    assert model == Model(
        "https://api.anthropic.com", "claude-opus-5-5", "reviewer-key", "anthropic"
    )


def test_any_other_endpoint_is_reached_as_an_openai_compatible_one():
    assert Model.reviewer(DEFAULT_URL, DEFAULT_NAME, None, KEYS).protocol == "openai"


def test_a_configured_protocol_wins_over_what_the_url_tells():
    gateway = Model.reviewer("https://gateway.example", "claude-opus-5-5", "anthropic", KEYS)

    assert gateway.protocol == "anthropic"


def test_the_reviewer_needs_its_key():
    with pytest.raises(MissingApiKey, match="RELECTEUR_API_KEY is not set"):
        Model.reviewer(DEFAULT_URL, DEFAULT_NAME, None, {})
