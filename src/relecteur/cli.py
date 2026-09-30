import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path

from relecteur import open_code_review, repository
from relecteur.cases import Case, InvalidCases, load_cases
from relecteur.model import MissingApiKey, Model
from relecteur.review import Review
from relecteur.scorer import Outcome, Report, evaluate

EXIT_CODES = {Outcome.PASSED: 0, Outcome.FAILED: 1, Outcome.ERROR: 3}
INVALID_INPUT = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="relecteur")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("eval", help="replay the validated cases and give a verdict")
    run.add_argument("cases", type=Path, help="a case file, or a directory of case files")
    run.add_argument("--repo", type=Path, help="evaluated repository (default: the one of CASES)")
    run.add_argument("--model", help="model name (default: $RELECTEUR_MODEL, then Albert's)")
    run.add_argument("--model-url", help="OpenAI-compatible endpoint (default: Albert)")

    validate = commands.add_parser("validate", help="check the format of case files")
    validate.add_argument("paths", type=Path, nargs="+", help="case files or directories")

    arguments = parser.parse_args(argv)
    if arguments.command == "validate":
        return _validate(arguments.paths)
    return _eval(arguments)


def _validate(paths: list[Path]) -> int:
    cases, problems = [], []
    for path in paths:
        try:
            cases += load_cases(path)
        except InvalidCases as invalid:
            problems += invalid.problems
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    drafts = sum(not case.validated for case in cases)
    print(f"{len(cases)} valid case(s): {len(cases) - drafts} validated, {drafts} draft")
    return 0


def _eval(arguments: argparse.Namespace) -> int:
    try:
        cases = load_cases(arguments.cases)
        model = Model.configure(os.environ, arguments.model_url, arguments.model)
        repo = (arguments.repo or repository.root(arguments.cases)).resolve()
    except (InvalidCases, MissingApiKey, repository.RepositoryError) as error:
        print(error, file=sys.stderr)
        return INVALID_INPUT
    print(
        f"{len(cases)} case(s) in {arguments.cases}, reviewed by {model.name} at {model.url}",
        flush=True,
    )
    report = evaluate(cases, _reviewer(repo, model))
    _print(report)
    return EXIT_CODES[report.outcome]


def _reviewer(repo: Path, model: Model) -> Callable[[Case], Review]:
    def review(case: Case) -> Review:
        print(f"reviewing {case.name} ({case.base[:10]}..{case.head[:10]})", file=sys.stderr)
        try:
            repository.ensure_commits(repo, case.base, case.head)
        except repository.RepositoryError as error:
            return Review(error=str(error))
        return open_code_review.review(repo, case.base, case.head, model)

    return review


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
