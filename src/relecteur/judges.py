"""Judges of expected defects: each gives the probability that a finding describes a defect.

The scorer receives a judge and never imports this module: changing judge touches nothing else.
"""

import json
import math
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any

from relecteur.cases import ExpectedDefect
from relecteur.model import MissingApiKey, Model
from relecteur.review import Finding
from relecteur.scorer import Judge, JudgeUnavailable

DEFAULT_MODELS = MappingProxyType({"albert": "deepseek-v4-flash-0731", "jev": "jev-latest"})

_JEV_URL = "https://api.typesafe.ai/v1/systemone"
_QUESTION = "Does the review remark point out the expected defect, even in other words?"


def from_environment(
    environ: Mapping[str, str], name: str, model: str | None, endpoint: Model
) -> Judge:
    """The judge called `name`, asking `model` or the judge's default one.

    The albert judge asks a model of the endpoint the reviewer uses, Albert unless configured
    otherwise; the jev judge reads its API key from TYPESAFE_API_KEY.
    """
    model = model or DEFAULT_MODELS[name]
    if name == "albert":
        return AlbertJudge(replace(endpoint, name=model))
    api_key = environ.get("TYPESAFE_API_KEY", "")
    if not api_key:
        raise MissingApiKey(f"TYPESAFE_API_KEY is not set: it holds the API key of {_JEV_URL}")
    return JevJudge(model, api_key)


@dataclass(frozen=True)
class AlbertJudge:
    """Asks a chat model to answer yes or no, and reads the probability of yes in its logprobs."""

    model: Model

    def __call__(self, finding: Finding, defect: ExpectedDefect) -> float:
        response = _post(
            f"{self.model.url.rstrip('/')}/chat/completions",
            self.model.api_key,
            {
                "model": self.model.name,
                "messages": [
                    {
                        "role": "system",
                        "content": "You compare a code review remark with a defect known to be "
                        "in the same pull request. Answer with a single word: yes or no.",
                    },
                    {"role": "user", "content": f"{_situation(finding, defect)}\n\n{_QUESTION}"},
                ],
                "max_tokens": 1,
                "temperature": 0,
                "logprobs": True,
                "top_logprobs": 5,
            },
        )
        return albert_probability(response)


@dataclass(frozen=True)
class JevJudge:
    """Asks Jev, TypeSafe's judgment model, which answers yes or no with a probability."""

    model: str
    api_key: str = field(repr=False)

    def __call__(self, finding: Finding, defect: ExpectedDefect) -> float:
        response = _post(
            _JEV_URL,
            self.api_key,
            {
                "model": self.model,
                "state": _situation(finding, defect),
                "questions": {"same_defect": {"type": "noul", "instructions": _QUESTION}},
            },
        )
        try:
            return float(response["answers"]["same_defect"]["noul"])
        except (KeyError, TypeError, ValueError) as error:
            raise JudgeUnavailable(f"unexpected answer of the jev judge: {error!r}") from error


def albert_probability(response: Mapping[str, Any]) -> float:
    """The probability of yes, read in the logprobs of the first token of a chat completion."""
    try:
        candidates = response["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
    except (KeyError, IndexError, TypeError) as error:
        raise JudgeUnavailable(f"the albert judge answered without logprobs: {error!r}") from error
    yes, no = _word_probability(candidates, "yes"), _word_probability(candidates, "no")
    if not yes + no:
        tokens = ", ".join(repr(candidate["token"]) for candidate in candidates)
        raise JudgeUnavailable(f"the albert judge answered neither yes nor no: {tokens}")
    return yes / (yes + no)


def _word_probability(candidates, word):
    return sum(
        math.exp(candidate["logprob"])
        for candidate in candidates
        if candidate["token"].strip().lower() == word
    )


def _situation(finding, defect):
    return (
        f"Expected defect, at {defect.path}:{defect.line}:\n{defect.concept}\n\n"
        f"Review remark, at {finding.path}:{finding.start_line}-{finding.end_line}:\n"
        f"{finding.text}"
    )


def _post(url, api_key, body):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise JudgeUnavailable(f"judge unavailable: {url} answered HTTP {error.code}") from error
    except OSError as error:
        raise JudgeUnavailable(f"judge unavailable: {url} unreachable ({error})") from error
    except json.JSONDecodeError as error:
        raise JudgeUnavailable(f"judge unavailable: {url} answered no JSON") from error
