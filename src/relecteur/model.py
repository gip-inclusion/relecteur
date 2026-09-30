from collections.abc import Mapping
from dataclasses import dataclass, field

DEFAULT_URL = "https://albert.api.etalab.gouv.fr/v1"
DEFAULT_NAME = "deepseek-v4-flash"


class MissingApiKey(Exception):
    pass


@dataclass(frozen=True)
class Model:
    """A model served behind an OpenAI-compatible endpoint: Albert unless configured otherwise."""

    url: str
    name: str
    api_key: str = field(repr=False)

    @classmethod
    def configure(
        cls, environ: Mapping[str, str], url: str | None = None, name: str | None = None
    ) -> "Model":
        """Reads the model from the call arguments, then the environment, then the defaults."""
        api_key = environ.get("RELECTEUR_API_KEY", "")
        if not api_key:
            raise MissingApiKey(
                "RELECTEUR_API_KEY is not set: it holds the API key of the model endpoint "
                f"({url or environ.get('RELECTEUR_MODEL_URL') or DEFAULT_URL})"
            )
        return cls(
            url=url or environ.get("RELECTEUR_MODEL_URL") or DEFAULT_URL,
            name=name or environ.get("RELECTEUR_MODEL") or DEFAULT_NAME,
            api_key=api_key,
        )
