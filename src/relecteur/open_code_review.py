"""Adapter for the open-code-review engine: the only module that knows its command line and output.

Changing engine means writing another module that turns a pull request into a `Review`.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from relecteur.model import Model
from relecteur.review import Finding, Review

_INSTALL_COMMAND = "npm install --global @alibaba-group/open-code-review@1.12.13"

# Statuses of a run that covered every file it selected (the last two come without a manifest).
_COMPLETE = frozenset({"complete", "success", "completed_with_warnings"})
# Failure classes of a model or an engine out of reach, rather than of an unfinished review.
_UNAVAILABLE = frozenset({"provider", "timeout", "cancelled"})

# A run cut short by the model's rate limit or by timeouts is resumed this many times, after a
# pause that doubles from one resume to the next, for a per-minute rate limit to recover.
_RESUMES = 3
_FIRST_RESUME_PAUSE_SECONDS = 60

EFFORTS = ("low", "medium", "high")


@dataclass(frozen=True)
class Settings:
    """How the engine reviews.

    Its effort preset, how many groups of files it reviews at once, the tokens it may spend on a
    review, and the language of its findings. A higher effort spends more rounds and tokens on
    each group; each group sends its own requests to the model, so concurrency is what runs into a
    model's rate limit. Without a budget, a review spends what it needs; without a language,
    findings come in English.
    """

    effort: str = "high"
    concurrency: int = 2
    max_tokens_budget: int | None = None
    language: str | None = None


class InvalidSettings(Exception):
    pass


def load_settings(path: Path) -> Settings:
    """The settings of a TOML file, the defaults standing for those it leaves out.

    Without such a file, the settings are all the defaults.
    """
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings()
    except tomllib.TOMLDecodeError as error:
        raise InvalidSettings(f"{path}: not valid TOML: {error}") from error
    for name, value in data.items():
        if name not in _SETTINGS:
            raise InvalidSettings(f"{path}: unknown setting '{name}'")
        is_valid, expectation = _SETTINGS[name]
        if not is_valid(value):
            raise InvalidSettings(f"{path}: '{name}' must be {expectation}, got {value!r}")
    return Settings(**data)


def _is_positive(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_text(value):
    return isinstance(value, str) and bool(value.strip())


_SETTINGS = {
    "effort": (lambda value: value in EFFORTS, f"one of {', '.join(EFFORTS)}"),
    "concurrency": (_is_positive, "a positive integer"),
    "max_tokens_budget": (_is_positive, "a positive integer"),
    "language": (_is_text, "a non-empty string"),
}


def review(
    repo: Path,
    base: str,
    head: str,
    model: Model,
    settings: Settings,
    background: str | None = None,
    instructions: str | None = None,
) -> Review:
    """Reviews `head` against its merge base with `base`, as the pull request was opened.

    `background` tells the engine what the pull request intends, and `instructions` replace its
    own rules on every file; the files it reviews remain those the repository's
    `.opencodereview/rule.json` selects.

    When the model's rate limit or timeouts cut the run short, it is resumed after a pause, longer
    at each resume: the engine then reviews the files left only, its session being kept in the
    home directory of the review.
    """
    command = ["ocr", "review", "--repo", str(repo), "--from", base, "--to", head]
    command += ["--effort", settings.effort, "--concurrency", str(settings.concurrency)]
    command += ["--format", "json", "--audience", "agent"]
    if settings.max_tokens_budget:
        command += ["--max-tokens-budget", str(settings.max_tokens_budget)]
    if background:
        command += ["--background", background]
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as home:
        if instructions:
            rule = json.dumps(rule_file(instructions), ensure_ascii=False)
            Path(home, "rule.json").write_text(rule, encoding="utf-8")
            command += ["--rule", str(Path(home, "rule.json"))]
        try:
            if settings.language and (
                error := _configure(model, home, "language", settings.language)
            ):
                return Review(error=error)
            runs = [_run(command, model, home)]
            for attempt in range(1, _RESUMES + 1):
                if not (session := session_to_resume(runs[-1].stdout)):
                    break
                pause = _FIRST_RESUME_PAUSE_SECONDS * 2 ** (attempt - 1)
                print(
                    f"  cut short, resuming in {pause} s ({attempt} of {_RESUMES})",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(pause)
                runs.append(_run([*command, "--resume", session], model, home))
        except FileNotFoundError:
            return Review(error=f"open-code-review is not installed (ocr): {_INSTALL_COMMAND}")
    reviews = [parse(run.stdout, run.stderr, run.returncode) for run in runs]
    return replace(
        reviews[-1],
        tokens=sum(review.tokens or 0 for review in reviews),
        seconds=time.monotonic() - started,
    )


def rule_file(instructions: str | None) -> dict:
    """The engine's rule file applying `instructions` to every file.

    The engine has a rule of its own for Python, which the instructions join, and for a few other
    file types (Maven, Gradle, package.json…); the instructions replace those, and the default rule
    every other file gets, which leads the reviewer to remarks on naming and test coverage. Without
    instructions, the engine keeps its own rules.
    """
    if not instructions:
        return {"rules": []}
    return {
        "rules": [
            {"path": "**/*.py", "rule": instructions, "merge_system_rule": True},
            {"path": "**/*", "rule": instructions},
        ]
    }


def session_to_resume(stdout: str) -> str | None:
    """The session of a run that the model's rate limit (HTTP 429) or timeouts cut short.

    Resuming it reviews the files left only. Other failures are not resumed: a reviewer that did
    not finish would end the same way, and a model failing otherwise may not recover in minutes.
    """
    try:
        output = json.loads(stdout)
        if output["status"] in _COMPLETE or output["status"] == "skipped":
            return None
        classes = _failure_classes(output)
        status_codes = {attempt.get("status_code") for attempt in _last_failed_attempts(output)}
        transient = bool(classes) and classes <= {"provider", "timeout"} and status_codes <= {429}
        return output.get("session_id") if transient else None
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _configure(model, home, key, value):
    """Sets a key of the engine's configuration in the home of the review, as `ocr config set`."""
    completed = _run(["ocr", "config", "set", key, value], model, home)
    if completed.returncode != 0:
        return f"open-code-review could not set its {key}: {completed.stderr.strip()}"
    return None


def _run(command, model, home):
    return subprocess.run(
        command, capture_output=True, text=True, check=False, env=_environment(model, home)
    )


def _environment(model, home):
    environment = {
        **os.environ,
        # The engine reads ~/.opencodereview/config.json before its environment variables:
        # an empty home leaves the model configured here as the only one in effect, while git
        # keeps the global configuration of the real home (safe.directory, credentials).
        "HOME": home,
        "OCR_LLM_URL": model.url,
        "OCR_LLM_TOKEN": model.api_key,
        "OCR_LLM_MODEL": model.name,
        "OCR_LLM_PROTOCOL": "openai",
    }
    environment.setdefault("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    if (Path.home() / ".gitconfig").exists():
        environment.setdefault("GIT_CONFIG_GLOBAL", str(Path.home() / ".gitconfig"))
    return environment


def parse(stdout: str, stderr: str, returncode: int) -> Review:
    """Turns the output of `ocr review --format json` into a `Review`.

    A review that did not cover every file gives no findings, since it cannot tell whether the
    reviewer would have stayed silent: it is an error when the model or the engine was out of
    reach, and an unfinished review otherwise.
    """
    try:
        output = json.loads(stdout)
    except json.JSONDecodeError:
        last_line = stderr.strip().splitlines()[-1] if stderr.strip() else "no output"
        return Review(error=f"open-code-review exited with code {returncode}: {last_line}")
    try:
        tokens = (output.get("summary") or {}).get("total_tokens")
        if output["status"] == "skipped":
            return Review(
                error="no file reviewed: the engine supports none of the files this pull request "
                "changes"
            )
        if output["status"] not in _COMPLETE:
            return replace(_incomplete_review(output), tokens=tokens)
        return Review(
            findings=tuple(_finding(comment) for comment in output["comments"]), tokens=tokens
        )
    except (AttributeError, KeyError, TypeError) as error:
        return Review(error=f"unexpected open-code-review output: {error!r}")


def _finding(comment):
    return Finding(
        path=comment["path"],
        start_line=comment["start_line"],
        end_line=comment["end_line"],
        text=comment["content"],
        category=comment.get("category"),
        severity=comment.get("severity"),
    )


def _incomplete_review(output):
    manifest = output.get("manifest") or {}
    coverage = manifest.get("coverage", {})
    failed = coverage.get("failed", [])
    selected = coverage.get("selected", [])
    classes = _failure_classes(output)
    causes = _provider_errors(output) or sorted({item["classification"] for item in failed})
    if run_failure := manifest.get("run_failure"):
        causes.append(f"{run_failure['classification']}: {run_failure.get('reason', '')}")
    scope = f" ({len(failed)} of {len(selected)} file(s) not reviewed)" if selected else ""
    detail = ", ".join(causes) or output.get("message", output["status"])
    if classes <= _UNAVAILABLE:
        unavailable = "model unavailable, " if "provider" in classes else ""
        return Review(error=f"{unavailable}review incomplete{scope}: {detail}")
    return Review(unfinished=f"review not finished{scope}: {detail}")


def _failure_classes(output):
    """The classifications of the files a run did not review, and of the run itself."""
    manifest = output.get("manifest") or {}
    classes = {item["classification"] for item in manifest.get("coverage", {}).get("failed", [])}
    if run_failure := manifest.get("run_failure"):
        classes.add(run_failure["classification"])
    return classes


def _provider_errors(output):
    errors = []
    for attempt in _last_failed_attempts(output):
        error = attempt.get("error_class", "unknown")
        if status_code := attempt.get("status_code"):
            error += f" (HTTP {status_code})"
        if error not in errors:
            errors.append(error)
    return errors


def _last_failed_attempts(output):
    """The last attempt of each request to the model that the engine gave up retrying."""
    return [
        request["attempts"][-1]
        for request in (output.get("retry_report") or {}).get("requests", [])
        if request["outcome"] == "failed" and request["attempts"]
    ]
