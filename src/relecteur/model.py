from collections.abc import Mapping
from dataclasses import dataclass, field

DEFAULT_URL = "https://albert.api.etalab.gouv.fr/v1"
DEFAULT_NAME = "deepseek-v4-flash-0731"


class MissingApiKey(Exception):
    pass


@dataclass(frozen=True)
class Model:
    """A model served behind an OpenAI-compatible endpoint: Albert unless configured otherwise."""

    url: str
    name: str
    api_key: str = field(repr=False)

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str], url: str | None, name: str | None
    ) -> "Model":
        """The model given by the call arguments, then the environment, then the defaults."""
        url = url or environ.get("RELECTEUR_MODEL_URL") or DEFAULT_URL
        api_key = environ.get("RELECTEUR_API_KEY", "")
        if not api_key:
            raise MissingApiKey(
                f"RELECTEUR_API_KEY is not set: it holds the API key of the model endpoint ({url})"
            )
        return cls(url, name or environ.get("RELECTEUR_MODEL") or DEFAULT_NAME, api_key)
