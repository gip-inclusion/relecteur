import argparse
import os
import sys
from collections import Counter
from contextlib import suppress
from dataclasses import replace
from pathlib import Path

from relecteur import judges, open_code_review, proxy, repository
from relecteur.cases import InvalidCases, load_cases
from relecteur.model import MissingApiKey, Model, endpoint_url
from relecteur.repository import CASES
from relecteur.review import Review
from relecteur.scorer import DEFAULT_LINE_TOLERANCE, DEFAULT_THRESHOLD, Matching, Outcome, evaluate

EXIT_CODES = {Outcome.PASSED: 0, Outcome.FAILED: 1, Outcome.ERROR: 3}
INVALID_INPUT = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="relecteur")
    commands = parser.add_subparsers(dest="command", required=True)

    eval_command = commands.add_parser("eval", help="replay the cases and give a verdict")
    eval_command.add_argument(
        "cases", type=Path, nargs="?", help=f"a case file or directory (default: {CASES})"
    )
    eval_command.add_argument(
        "--model", help="model name (default: $RELECTEUR_MODEL, then Albert's)"
    )
    eval_command.add_argument("--model-url", help="OpenAI-compatible endpoint (default: Albert)")
    eval_command.add_argument(
        "--judge",
        choices=sorted(judges.DEFAULT_MODELS),
        default="albert",
        help="judge of expected defects (default: albert)",
    )
    eval_command.add_argument(
        "--judge-model",
        help="model of the judge (default: "
        + ", ".join(f"{model} for {judge}" for judge, model in judges.DEFAULT_MODELS.items())
        + ")",
    )
    eval_command.add_argument(
        "--judge-threshold",
        type=_probability,
        default=DEFAULT_THRESHOLD,
        help=f"probability from which the judge confirms a defect (default: {DEFAULT_THRESHOLD})",
    )
    eval_command.add_argument(
        "--line-tolerance",
        type=_line_count,
        default=DEFAULT_LINE_TOLERANCE,
        help="lines between a finding and an expected defect for the judge to be asked "
        f"(default: {DEFAULT_LINE_TOLERANCE})",
    )

    defaults = open_code_review.Settings()
    eval_command.add_argument(
        "--effort",
        choices=open_code_review.EFFORTS,
        default=defaults.effort,
        help=f"review effort preset of the engine (default: {defaults.effort})",
    )
    eval_command.add_argument(
        "--concurrency",
        type=_concurrency,
        default=defaults.concurrency,
        help="groups of files the engine reviews at once, each sending its own requests to the "
        f"model (default: {defaults.concurrency})",
    )

    validate_command = commands.add_parser("validate", help="check the format of case files")
    validate_command.add_argument(
        "paths", type=Path, nargs="*", help=f"case files or directories (default: {CASES})"
    )

    proxy_command = commands.add_parser("proxy", help="relay the model endpoint for an engine run")
    proxy_command.add_argument("--port", type=int, default=8765, help="local port (default: 8765)")
    proxy_command.add_argument("--model-url", help="OpenAI-compatible endpoint (default: Albert)")

    arguments = parser.parse_args(argv)
    if arguments.command == "validate":
        return _validate(arguments.paths)
    if arguments.command == "proxy":
        return _proxy(arguments.port, endpoint_url(os.environ, arguments.model_url))
    return _eval(arguments)


def _validate(paths):
    try:
        cases = load_cases(*(paths or [repository.cases_directory(Path.cwd())]))
    except (InvalidCases, repository.RepositoryError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"{len(cases)} valid case(s)")
    return 0


def _eval(arguments):
    try:
        path = arguments.cases or repository.cases_directory(Path.cwd())
        cases = load_cases(path)
        model = Model.from_environment(os.environ, arguments.model_url, arguments.model)
        judge = judges.from_environment(os.environ, arguments.judge, arguments.judge_model, model)
        repo = repository.root(path).resolve()
    except (InvalidCases, MissingApiKey, repository.RepositoryError) as error:
        print(error, file=sys.stderr)
        return INVALID_INPUT
    print(
        f"{len(cases)} case(s) in {path}, reviewed by {model.name} at {model.url}",
        flush=True,
    )
    engine = open_code_review.Settings(arguments.effort, arguments.concurrency)
    with proxy.relaying(model.url) as relay_url:
        reviews = {
            case: _review(case, repo, replace(model, url=relay_url), engine) for case in cases
        }
    report = evaluate(
        cases, reviews, Matching(judge, arguments.line_tolerance, arguments.judge_threshold)
    )
    _print(report)
    return EXIT_CODES[report.outcome]


def _proxy(port, upstream):
    print(f"relaying http://127.0.0.1:{port} to {upstream}, until interrupted", flush=True)
    with suppress(KeyboardInterrupt):
        proxy.serve(upstream, port)
    return 0


def _review(case, repo, model, engine):
    print(f"reviewing {case.name} ({case.base[:10]}..{case.head[:10]})", file=sys.stderr)
    try:
        repository.ensure_commits(repo, case.base, case.head)
    except repository.RepositoryError as error:
        return Review(error=str(error))
    return open_code_review.review(repo, case.base, case.head, model, engine)


def _probability(text):
    value = float(text)
    if not 0 <= value <= 1:
        raise argparse.ArgumentTypeError(f"must be between 0 and 1, got {text}")
    return value


def _concurrency(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {text}")
    return value


def _line_count(text):
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"must be a non-negative number of lines, got {text}")
    return value


def _print(report):
    print()
    for result in report.results:
        summary = "; ".join(result.reasons) or (
            f"{len(result.findings)} finding(s), ceiling is {result.case.max_findings}"
        )
        print(f"{result.outcome.name:<8} {result.case.name}: {summary}")
        for finding in result.findings:
            text = finding.text.splitlines()[0] if finding.text else ""
            print(f"         {finding.path}:{finding.start_line}: {text}")
        for defect_result in result.defects:
            print(f"         {_defect_line(defect_result)}")
    silence = [result for result in report.results if not result.case.expected_defects]
    defect_cases = [result for result in report.results if result.case.expected_defects]
    print(f"\nsilence cases: {_counts(silence)}")
    if defect_cases:
        print(f"defect cases: {_counts(defect_cases)}, reported without deciding the verdict")
        print(
            _coverage(
                [defect_result for result in defect_cases for defect_result in result.defects]
            )
        )
    print(f"verdict: {report.outcome.name}")


def _defect_line(result):
    defect = result.defect
    status = "found" if result.found else "missed"
    escaped = ", which the human review let through" if defect.escaped_review else ""
    if result.finding is None:
        return f"{status} defect at {defect.location}{escaped}: no finding near it"
    return (
        f"{status} defect at {defect.location}{escaped}: the judge gives "
        f"{result.probability:.2f} to {result.finding.path}:{result.finding.start_line}"
    )


def _counts(results):
    counts = Counter(result.outcome for result in results)
    return (
        f"{counts[Outcome.PASSED]} passed, {counts[Outcome.FAILED]} failed, "
        f"{counts[Outcome.ERROR]} error(s)"
    )


def _coverage(defect_results):
    escaped = [result for result in defect_results if result.defect.escaped_review]
    return (
        f"defects found: {sum(result.found for result in defect_results)} "
        f"of {len(defect_results)}, "
        f"{sum(result.found for result in escaped)} of {len(escaped)} "
        "among those the human review let through"
    )
