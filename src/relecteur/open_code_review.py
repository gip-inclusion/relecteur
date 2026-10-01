"""Adapter for the open-code-review engine: the only module that knows its command line and output.

Changing engine means writing another module that turns a pull request into a `Review`.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from relecteur.model import Model
from relecteur.review import Finding, Review

INSTALL = "npm install --global @alibaba-group/open-code-review@1.12.11"

# Statuses of a run that covered every file it selected (the last two predate the run manifest).
_COMPLETE = ("complete", "skipped", "success", "completed_with_warnings")


def review(repo: Path, base: str, head: str, model: Model) -> Review:
    """Reviews `head` against its merge base with `base`, as the pull request was opened."""
    command = ["ocr", "review", "--repo", str(repo), "--from", base, "--to", head]
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
            return Review(error=f"open-code-review is not installed (ocr): {INSTALL}")
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

    A review that did not cover every file is an error rather than a partial list of findings:
    it cannot tell whether the reviewer would have stayed silent.
    """
    try:
        output = json.loads(stdout)
    except json.JSONDecodeError:
        last_line = stderr.strip().splitlines()[-1] if stderr.strip() else "no output"
        return Review(error=f"open-code-review exited with code {returncode}: {last_line}")
    try:
        if output["status"] not in _COMPLETE:
            return Review(error=_incompleteness_error(output))
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


def _incompleteness_error(output):
    manifest = output.get("manifest") or {}
    coverage = manifest.get("coverage", {})
    failed = coverage.get("failed", [])
    selected = coverage.get("selected", [])
    causes = _provider_errors(output) or sorted({item["classification"] for item in failed})
    if run_failure := manifest.get("run_failure"):
        causes.append(f"{run_failure['classification']}: {run_failure.get('reason', '')}")
    unavailable = any(item["classification"] == "provider" for item in failed)
    scope = f" ({len(failed)} of {len(selected)} file(s) not reviewed)" if selected else ""
    return (
        ("model unavailable, " if unavailable else "")
        + f"review incomplete{scope}: "
        + (", ".join(causes) or output.get("message", output["status"]))
    )


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
