from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlparse

DEFAULT_URL = "https://albert.api.etalab.gouv.fr/v1"
DEFAULT_NAME = "deepseek-v4-flash-0731"
# OpenAI's chat completions, which Albert serves, and Anthropic's Messages API.
PROTOCOLS = ("openai", "anthropic")

_ANTHROPIC_HOST = "api.anthropic.com"


class MissingApiKey(Exception):
    pass


@dataclass(frozen=True)
class Model:
    """A model and the endpoint that serves it, through one of the `PROTOCOLS`."""

    url: str
    name: str
    api_key: str = field(repr=False)
    protocol: str = "openai"

    @classmethod
    def reviewer(
        cls, url: str, name: str, protocol: str | None, environ: Mapping[str, str]
    ) -> "Model":
        """The model that reviews, with its key from RELECTEUR_API_KEY."""
        api_key = environ.get("RELECTEUR_API_KEY", "")
        if not api_key:
            raise MissingApiKey(
                f"RELECTEUR_API_KEY is not set: it holds the API key of the reviewer's endpoint "
                f"({url})"
            )
        return cls(url, name, api_key, protocol_of(url, protocol))


def protocol_of(url: str, protocol: str | None) -> str:
    """The protocol of an endpoint: the one given, else Anthropic's for Anthropic's API, and
    OpenAI's otherwise."""
    if protocol:
        return protocol
    return "anthropic" if urlparse(url).hostname == _ANTHROPIC_HOST else "openai"
