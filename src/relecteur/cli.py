import argparse
import os
import sys
from contextlib import suppress
from dataclasses import replace
from pathlib import Path

from relecteur import open_code_review, proxy, repository
from relecteur.cases import Case, InvalidCases, load_cases
from relecteur.model import MissingApiKey, Model, endpoint_url
from relecteur.review import Review
from relecteur.scorer import Outcome, Report, evaluate

EXIT_CODES = {Outcome.PASSED: 0, Outcome.FAILED: 1, Outcome.ERROR: 3, Outcome.PENDING: 3}
INVALID_INPUT = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="relecteur")
    commands = parser.add_subparsers(dest="command", required=True)

    evaluation = commands.add_parser("eval", help="replay the validated cases and give a verdict")
    evaluation.add_argument("cases", type=Path, help="a case file, or a directory of case files")
    evaluation.add_argument("--repo", type=Path, help="evaluated repository (default: CASES's)")
    evaluation.add_argument("--model", help="model name (default: $RELECTEUR_MODEL, then Albert's)")
    evaluation.add_argument("--model-url", help="OpenAI-compatible endpoint (default: Albert)")

    validate = commands.add_parser("validate", help="check the format of case files")
    validate.add_argument("paths", type=Path, nargs="+", help="case files or directories")

    relay = commands.add_parser("proxy", help="relay the model endpoint for a direct engine run")
    relay.add_argument("--port", type=int, default=8765, help="local port (default: 8765)")
    relay.add_argument("--model-url", help="OpenAI-compatible endpoint (default: Albert)")

    arguments = parser.parse_args(argv)
    if arguments.command == "validate":
        return _validate(arguments.paths)
    if arguments.command == "proxy":
        return _proxy(arguments.port, endpoint_url(os.environ, arguments.model_url))
    return _eval(arguments)


def _validate(paths: list[Path]) -> int:
    try:
        cases = load_cases(*paths)
    except InvalidCases as invalid:
        print(invalid, file=sys.stderr)
        return 1
    drafts = sum(not case.validated for case in cases)
    print(f"{len(cases)} valid case(s): {len(cases) - drafts} validated, {drafts} draft")
    return 0


def _eval(arguments: argparse.Namespace) -> int:
    try:
        cases = load_cases(arguments.cases)
        model = Model.from_environment(os.environ, arguments.model_url, arguments.model)
        repo = (arguments.repo or repository.root(arguments.cases)).resolve()
    except (InvalidCases, MissingApiKey, repository.RepositoryError) as error:
        print(error, file=sys.stderr)
        return INVALID_INPUT
    print(
        f"{len(cases)} case(s) in {arguments.cases}, reviewed by {model.name} at {model.url}",
        flush=True,
    )
    with proxy.relaying(model.url) as relay_url:
        relayed = replace(model, url=relay_url)
        reviews = {case: _review(case, repo, relayed) for case in cases if case.validated}
    report = evaluate(cases, reviews)
    _print(report)
    return EXIT_CODES[report.outcome]


def _proxy(port: int, upstream: str) -> int:
    print(f"relaying http://127.0.0.1:{port} to {upstream}, until interrupted", flush=True)
    with suppress(KeyboardInterrupt):
        proxy.serve(upstream, port)
    return 0


def _review(case: Case, repo: Path, model: Model) -> Review:
    print(f"reviewing {case.name} ({case.base[:10]}..{case.head[:10]})", file=sys.stderr)
    try:
        repository.ensure_commits(repo, case.base, case.head)
    except repository.RepositoryError as error:
        return Review(error=str(error))
    return open_code_review.review(repo, case.base, case.head, model)


def _print(report: Report) -> None:
    print()
    for result in report.results:
        summary = "; ".join(result.reasons) or (
            f"{len(result.findings)} finding(s), ceiling is {result.case.max_findings}"
        )
        print(f"{result.outcome.name:<8} {result.case.name}: {summary}")
        for finding in result.findings:
            text = finding.text.splitlines()[0] if finding.text else ""
            print(f"         {finding.path}:{finding.start_line}: {text}")
    for case in report.pending:
        print(f"{'PENDING':<8} {case.name}: draft, awaiting human validation")
    counts = {
        outcome: sum(result.outcome is outcome for result in report.results) for outcome in Outcome
    }
    print(
        f"\nverdict: {report.outcome.name} ({counts[Outcome.PASSED]} passed, "
        f"{counts[Outcome.FAILED]} failed, {counts[Outcome.ERROR]} error(s), "
        f"{len(report.pending)} pending)"
    )
