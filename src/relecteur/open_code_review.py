"""Adapter for the open-code-review engine: the only module that knows its command line and output.

Changing engine means writing another module that turns a pull request into a `Review`.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from relecteur.model import Model
from relecteur.review import Finding, PullRequestReview, Review, Status

_INSTALL_COMMAND = "npm install --global @alibaba-group/open-code-review@1.12.13"

# Statuses of a run that covered every file it selected (the last two come without a manifest).
_COMPLETE_STATUSES = frozenset({"complete", "success", "completed_with_warnings"})
# Failure classes of a model or an engine out of reach, rather than of an unfinished review.
_UNAVAILABLE_CLASSES = frozenset({"provider", "timeout", "cancelled"})
# Errors of a model out of reach for a while, unlike a refused key or request; the engine classes
# the other 5xx answers, such as 503, as "provider" errors, along with refused requests.
_TRANSIENT_ERROR_CLASSES = frozenset({"rate_limited", "overloaded", "timeout", "network"})

# A run cut short by the model's rate limit or by timeouts is resumed this many times, after a
# pause that doubles from one resume to the next, for a per-minute rate limit to recover.
_RESUMES = 3
_FIRST_RESUME_PAUSE_SECONDS = 60

EFFORTS = ("low", "medium", "high")


@dataclass(frozen=True)
class Settings:
    """How the engine reviews.

    Its effort preset, how many groups of files it reviews at once, the tokens it may spend on a
    review, the language of its findings, and the files it reviews: `include` adds files it leaves
    out by default (tests, templates), `exclude` takes files out, whatever `include` says. A higher
    effort spends more rounds and tokens on each group; each group sends its own requests to the
    model, so concurrency is what runs into a model's rate limit. Without a budget, a review spends
    what it needs.
    """

    effort: str = "high"
    concurrency: int = 2
    max_tokens_budget: int | None = None
    language: str = "French"
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


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
    own rules on every file; the settings select the files it reviews.

    When the model's rate limit or timeouts cut the run short, it is resumed after a pause, longer
    at each resume: the engine then reviews the files left only, its session being kept in the
    home directory of the review.
    """
    started = time.monotonic()
    try:
        runs = _runs(repo, base, head, model, settings, background, instructions)
    except _EngineError as error:
        return Review(error=str(error))
    reviews = [parse(run.stdout, run.stderr, run.returncode) for run in runs]
    return replace(
        reviews[-1],
        tokens=sum(review.tokens or 0 for review in reviews),
        seconds=time.monotonic() - started,
    )


def pull_request_output(
    repo: Path,
    base: str,
    head: str,
    model: Model,
    settings: Settings,
    background: str | None = None,
    instructions: str | None = None,
) -> tuple[str, str]:
    """Reviews a pull request in CI as `review` does, and gives what `pull_request_review` reads:
    the engine's output after its last resume, which holds the findings of every run, and its
    error output."""
    try:
        runs = _runs(repo, base, head, model, settings, background, instructions)
    except _EngineError as error:
        return "", str(error)
    return runs[-1].stdout, "".join(run.stderr for run in runs)


def rule_file(
    instructions: str | None, include: Sequence[str] = (), exclude: Sequence[str] = ()
) -> dict:
    """The engine's rule file applying `instructions` to every file, among the files that
    `include` and `exclude` select.

    The instructions replace the engine's own rules: one per language or file type (Java, Go,
    TypeScript, YAML…), and the default rule every other file gets, which leads the reviewer to
    remarks on naming and test coverage. Without instructions, the engine keeps its own rules.
    """
    rule: dict = {"rules": []}
    if instructions:
        rule["rules"] = [{"path": "**/*", "rule": instructions}]
    if include:
        rule["include"] = list(include)
    if exclude:
        rule["exclude"] = list(exclude)
    return rule


def session_to_resume(stdout: str) -> str | None:
    """The session of a run that the model's rate limit (HTTP 429) or timeouts cut short.

    Resuming it reviews the files left only. Other failures are not resumed: a reviewer that did
    not finish would end the same way, and a model failing otherwise may not recover in minutes.
    """
    try:
        output = json.loads(stdout)
        if output["status"] in _COMPLETE_STATUSES or output["status"] == "skipped":
            return None
        classes = _failure_classes(output)
        # A request that got no HTTP response, such as one that timed out, has no status code.
        status_codes = {attempt.get("status_code") for attempt in _last_failed_attempts(output)}
        transient = (
            bool(classes) and classes <= {"provider", "timeout"} and status_codes <= {429, None}
        )
        return output.get("session_id") if transient else None
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


class _EngineError(Exception):
    pass


def _runs(repo, base, head, model, settings, background, instructions):
    """The engine's run, then its resumes while the model's rate limit or timeouts cut it short."""
    command = ["ocr", "review", "--repo", str(repo), "--from", base, "--to", head]
    command += ["--effort", settings.effort, "--concurrency", str(settings.concurrency)]
    command += ["--format", "json", "--audience", "agent"]
    if settings.max_tokens_budget:
        command += ["--max-tokens-budget", str(settings.max_tokens_budget)]
    if background:
        command += ["--background", background]
    with tempfile.TemporaryDirectory() as home:
        if instructions or settings.include or settings.exclude:
            rule = rule_file(instructions, settings.include, settings.exclude)
            Path(home, "rule.json").write_text(json.dumps(rule, ensure_ascii=False), "utf-8")
            command += ["--rule", str(Path(home, "rule.json"))]
        try:
            if error := _configure(model, home, "language", settings.language):
                raise _EngineError(error)
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
            raise _EngineError(
                f"open-code-review is not installed (ocr): {_INSTALL_COMMAND}"
            ) from None
    return runs


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
        "OCR_LLM_PROTOCOL": model.protocol,
        # Left alone, the engine's launcher installs its latest version in the background, and a
        # resume would then run with other built-in rules than the pinned version it resumes.
        "OCR_NO_UPDATE": "1",
    }
    if model.protocol == "anthropic":
        # Anthropic's API takes an API key in x-api-key, where the engine sends a bearer token.
        environment["OCR_LLM_AUTH_HEADER"] = "x-api-key"
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
        return Review(error=f"open-code-review exited with code {returncode}: {_last_line(stderr)}")
    try:
        tokens = (output.get("summary") or {}).get("total_tokens")
        if output["status"] == "skipped":
            return Review(
                error="no file reviewed: the engine supports none of the files this pull request "
                "changes"
            )
        if output["status"] not in _COMPLETE_STATUSES:
            return replace(_incomplete_review(output), tokens=tokens)
        return Review(findings=_findings(output["comments"]), tokens=tokens)
    except (AttributeError, KeyError, TypeError) as error:
        return Review(error=f"unexpected open-code-review output: {error!r}")


def pull_request_review(stdout: str, stderr: str) -> PullRequestReview:
    """Turns the output of `ocr review --format json` in CI into a `PullRequestReview`.

    Unlike `parse`, it keeps the findings of a review that did not cover every file: the review
    in CI publishes them.
    """
    try:
        output = json.loads(stdout)
    except json.JSONDecodeError:
        return PullRequestReview(Status.FAILED, cause=_last_line(stderr))
    try:
        if output["status"] in _COMPLETE_STATUSES:
            return PullRequestReview(Status.REVIEWED, _findings(output["comments"]))
        if output["status"] == "skipped":
            return PullRequestReview(Status.NOTHING_TO_REVIEW)
        coverage = (output.get("manifest") or {}).get("coverage", {})
        return PullRequestReview(
            _incomplete_review_status(output),
            _findings(output.get("comments") or []),
            files=len(coverage.get("selected", [])),
            unreviewed=len(coverage.get("failed", [])),
            cause=_failure_causes(output),
        )
    except (AttributeError, KeyError, TypeError) as error:
        return PullRequestReview(
            Status.FAILED, cause=f"unexpected open-code-review output: {error!r}"
        )


def _incomplete_review_status(output):
    if (output.get("summary") or {}).get("budget_exceeded"):
        return Status.OVER_BUDGET
    if _failure_classes(output) <= _UNAVAILABLE_CLASSES and all(
        _is_transient(attempt) for attempt in _last_failed_attempts(output)
    ):
        return Status.UNAVAILABLE
    return Status.FAILED


def _last_line(stderr):
    return stderr.strip().splitlines()[-1] if stderr.strip() else "no output"


def _findings(comments):
    return tuple(_finding(comment) for comment in comments)


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
    scope = f" ({len(failed)} of {len(selected)} file(s) not reviewed)" if selected else ""
    detail = _failure_causes(output) or output.get("message", output["status"])
    if classes <= _UNAVAILABLE_CLASSES:
        unavailable = "model unavailable, " if "provider" in classes else ""
        return Review(error=f"{unavailable}review incomplete{scope}: {detail}")
    return Review(unfinished=f"review not finished{scope}: {detail}")


def _is_transient(attempt):
    error = attempt.get("error_class")
    return error in _TRANSIENT_ERROR_CLASSES or (
        error == "provider" and (attempt.get("status_code") or 0) >= 500
    )


def _failure_causes(output):
    """Why a run did not review every file: the model's errors, else how its files failed."""
    manifest = output.get("manifest") or {}
    failed = manifest.get("coverage", {}).get("failed", [])
    causes = _provider_errors(output) or sorted({item["classification"] for item in failed})
    if run_failure := manifest.get("run_failure"):
        causes.append(f"{run_failure['classification']}: {run_failure.get('reason', '')}")
    return ", ".join(causes)


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
