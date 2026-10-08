"""Adapter for the open-code-review engine: the only module that knows its command line and output.

Changing engine means writing another module that turns a pull request into a `Review`.
"""

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from relecteur.model import Model
from relecteur.review import Finding, Review

_INSTALL_COMMAND = "npm install --global @alibaba-group/open-code-review@1.12.11"

# Statuses of a run that covered every file it selected (the last two come without a manifest).
_COMPLETE = frozenset({"complete", "success", "completed_with_warnings"})
# Failure classes of a model or an engine out of reach, rather than of an unfinished review.
_UNAVAILABLE = frozenset({"provider", "timeout", "cancelled"})

EFFORTS = ("low", "medium", "high")


@dataclass(frozen=True)
class Settings:
    """How the engine reviews: its effort preset, and how many groups of files it reviews at once.

    A higher effort spends more rounds and tokens on each group; each group sends its own
    requests to the model, so concurrency is what runs into a model's rate limit.
    """

    effort: str = "high"
    concurrency: int = 2


def review(repo: Path, base: str, head: str, model: Model, settings: Settings) -> Review:
    """Reviews `head` against its merge base with `base`, as the pull request was opened."""
    command = ["ocr", "review", "--repo", str(repo), "--from", base, "--to", head]
    command += ["--effort", settings.effort, "--concurrency", str(settings.concurrency)]
    with tempfile.TemporaryDirectory() as home:
        try:
            completed = subprocess.run(
                [*command, "--format", "json", "--audience", "agent"],
                capture_output=True,
                text=True,
                check=False,
                env=_environment(model, home),
            )
        except FileNotFoundError:
            return Review(error=f"open-code-review is not installed (ocr): {_INSTALL_COMMAND}")
    return parse(completed.stdout, completed.stderr, completed.returncode)


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
        if output["status"] == "skipped":
            return Review(
                error="no file reviewed: the engine supports none of the files this pull request "
                "changes"
            )
        if output["status"] not in _COMPLETE:
            return _incomplete_review(output)
        return Review(findings=tuple(_finding(comment) for comment in output["comments"]))
    except (KeyError, TypeError) as error:
        return Review(error=f"unexpected open-code-review output: {error!r}")


def _finding(comment):
    return Finding(
        path=comment["path"],
        start_line=comment["start_line"],
        end_line=comment["end_line"],
        text=comment["content"],
    )


def _incomplete_review(output):
    manifest = output.get("manifest") or {}
    coverage = manifest.get("coverage", {})
    failed = coverage.get("failed", [])
    selected = coverage.get("selected", [])
    classes = {item["classification"] for item in failed}
    causes = _provider_errors(output) or sorted(classes)
    if run_failure := manifest.get("run_failure"):
        classes.add(run_failure["classification"])
        causes.append(f"{run_failure['classification']}: {run_failure.get('reason', '')}")
    scope = f" ({len(failed)} of {len(selected)} file(s) not reviewed)" if selected else ""
    detail = ", ".join(causes) or output.get("message", output["status"])
    if classes <= _UNAVAILABLE:
        unavailable = "model unavailable, " if "provider" in classes else ""
        return Review(error=f"{unavailable}review incomplete{scope}: {detail}")
    return Review(unfinished=f"review not finished{scope}: {detail}")


def _provider_errors(output):
    errors = []
    for request in (output.get("retry_report") or {}).get("requests", []):
        if request["outcome"] != "failed" or not request["attempts"]:
            continue
        last_attempt = request["attempts"][-1]
        error = last_attempt.get("error_class", "unknown")
        if status_code := last_attempt.get("status_code"):
            error += f" (HTTP {status_code})"
        if error not in errors:
            errors.append(error)
    return errors
