import argparse
import json
import os
import sys
import urllib.error
from collections import Counter
from contextlib import contextmanager, suppress
from dataclasses import replace
from pathlib import Path

from relecteur import config, github, judges, open_code_review, proxy, repository, summary
from relecteur.cases import InvalidCases, load_cases
from relecteur.config import InvalidConfig
from relecteur.model import DEFAULT_NAME, DEFAULT_URL, MissingApiKey, Model
from relecteur.repository import CASES, CONFIG
from relecteur.review import Review, load, save
from relecteur.scorer import (
    DEFAULT_LINE_TOLERANCE,
    DefectFinder,
    Outcome,
    evaluate,
)

EXIT_CODES = {Outcome.PASSED: 0, Outcome.FAILED: 1, Outcome.ERROR: 3}
INVALID_INPUT = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="relecteur")
    commands = parser.add_subparsers(dest="command", required=True)

    eval_command = commands.add_parser("eval", help="replay the cases and give a verdict")
    eval_command.add_argument(
        "cases", type=Path, nargs="*", help=f"case files or directories (default: {CASES})"
    )
    eval_command.add_argument(
        "--model", help=f"model that reviews (default: {CONFIG}, then {DEFAULT_NAME})"
    )
    eval_command.add_argument(
        "--model-url",
        help=f"endpoint of the model, OpenAI-compatible or Anthropic's API (default: {CONFIG}, "
        f"then {DEFAULT_URL})",
    )
    eval_command.add_argument(
        "--save-reviews",
        type=Path,
        metavar="DIR",
        help="write each review to DIR/<case>.json, for `relecteur score` to judge it again",
    )
    _add_scoring_arguments(eval_command)

    defaults = open_code_review.Settings()
    eval_command.add_argument(
        "--effort",
        choices=open_code_review.EFFORTS,
        help=f"review effort preset of the engine (default: {CONFIG}, then {defaults.effort})",
    )
    eval_command.add_argument(
        "--concurrency",
        type=_concurrency,
        help="groups of files the engine reviews at once, each sending its own requests to the "
        f"model (default: {CONFIG}, then {defaults.concurrency})",
    )

    score_command = commands.add_parser(
        "score", help="judge again the reviews saved by `eval --save-reviews`, without reviewing"
    )
    score_command.add_argument("reviews", type=Path, help="directory of the saved reviews")
    score_command.add_argument(
        "cases", type=Path, nargs="*", help=f"case files or directories (default: {CASES})"
    )
    _add_scoring_arguments(score_command)

    validate_command = commands.add_parser("validate", help="check the format of case files")
    validate_command.add_argument(
        "paths", type=Path, nargs="*", help=f"case files or directories (default: {CASES})"
    )

    commands.add_parser(
        "rule",
        help=f"print the engine rule file: REVIEW.md and AGENTS.md, on the files {CONFIG} selects",
    )

    review_pr_command = commands.add_parser(
        "review-pr", help="review a pull request in CI, by the repository's rules and settings"
    )
    review_pr_command.add_argument("--base", required=True, help="the pull request's merge base")
    review_pr_command.add_argument("--head", required=True, help="the pull request's last commit")
    review_pr_command.add_argument(
        "--background", help="what the pull request intends: its title, then its description"
    )
    review_pr_command.add_argument(
        "--output", type=Path, required=True, help="directory to write the review to"
    )

    post_review_command = commands.add_parser(
        "post-review", help="post a review of `relecteur review-pr` on its pull request"
    )
    post_review_command.add_argument("output", type=Path, help="directory of the review")
    post_review_command.add_argument("--pr", type=int, required=True, help="pull request number")
    post_review_command.add_argument("--head", required=True, help="the commit reviewed")

    proxy_command = commands.add_parser("proxy", help="relay the model endpoint for an engine run")
    proxy_command.add_argument("--port", type=int, default=8765, help="local port (default: 8765)")
    proxy_command.add_argument(
        "--model-url", help=f"OpenAI-compatible endpoint (default: {DEFAULT_URL})"
    )

    arguments = parser.parse_args(argv)
    if arguments.command == "validate":
        return _validate(arguments.paths)
    if arguments.command == "rule":
        return _rule()
    if arguments.command == "review-pr":
        return _review_pr(arguments)
    if arguments.command == "post-review":
        return _post_review(arguments)
    if arguments.command == "score":
        return _score(arguments)
    if arguments.command == "proxy":
        return _proxy(arguments.port, arguments.model_url or DEFAULT_URL)
    return _eval(arguments)


def _add_scoring_arguments(command):
    defaults = config.JudgeSettings()
    command.add_argument(
        "--judge",
        choices=sorted(judges.DEFAULT_MODELS),
        help=f"judge of expected defects (default: {CONFIG}, then {defaults.name})",
    )
    command.add_argument(
        "--judge-model",
        help=f"model of the judge (default: {CONFIG}, then "
        + ", ".join(f"{model} for {judge}" for judge, model in judges.DEFAULT_MODELS.items())
        + ")",
    )
    command.add_argument(
        "--judge-threshold",
        type=_probability,
        help="probability from which the judge confirms a defect "
        f"(default: {CONFIG}, then {defaults.threshold})",
    )
    command.add_argument(
        "--line-tolerance",
        type=_line_count,
        default=DEFAULT_LINE_TOLERANCE,
        help="lines between a finding and an expected defect for the judge to be asked "
        f"(default: {DEFAULT_LINE_TOLERANCE})",
    )


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
        paths, cases, repo, environ = _cases(arguments.cases)
        settings = _config(repo, arguments)
        reviewer = settings.model
        model = Model.reviewer(reviewer.url, reviewer.name, reviewer.protocol, environ)
        judge = judges.from_environment(environ, settings.judge.name, settings.judge.model, model)
    except (InvalidCases, InvalidConfig, MissingApiKey, repository.RepositoryError) as error:
        print(error, file=sys.stderr)
        return INVALID_INPUT
    instructions = repository.reviewer_instructions(repo)
    print(
        f"{len(cases)} case(s) in {', '.join(str(path) for path in paths)}, reviewed by "
        f"{model.name} at {model.url}\nengine: {_describe(settings.engine)}; "
        f"{_rules_followed(repo, instructions)}\njudge: {_judged_by(settings.judge)}",
        flush=True,
    )
    if arguments.save_reviews:
        arguments.save_reviews.mkdir(parents=True, exist_ok=True)
        _save_reviewer(model, arguments.save_reviews)
    reviews = {}
    with _reached(model) as engine_model:
        for case in cases:
            reviews[case] = _review(case, repo, engine_model, settings.engine, instructions)
            if arguments.save_reviews:
                save(reviews[case], arguments.save_reviews / f"{case.name}.json")
    return _report(cases, reviews, judge, settings.judge.threshold, arguments)


def _score(arguments):
    try:
        paths, cases, repo, environ = _cases(arguments.cases)
        settings = _config(repo, arguments).judge
        reviewer = _saved_reviewer(arguments.reviews, environ)
        judge = judges.from_environment(environ, settings.name, settings.model, reviewer)
    except (
        InvalidCases,
        InvalidConfig,
        InvalidReviews,
        MissingApiKey,
        repository.RepositoryError,
    ) as error:
        print(error, file=sys.stderr)
        return INVALID_INPUT
    print(
        f"{len(cases)} case(s) in {', '.join(str(path) for path in paths)}, reviewed by "
        f"{reviewer.name} at {reviewer.url}, as saved in {arguments.reviews}\n"
        f"judge: {_judged_by(settings)}",
        flush=True,
    )
    reviews = {case: _saved_review(arguments.reviews / f"{case.name}.json") for case in cases}
    return _report(cases, reviews, judge, settings.threshold, arguments)


def _rule():
    try:
        repo = repository.root(Path.cwd())
        engine = config.load(repo / CONFIG).engine
    except (InvalidConfig, repository.RepositoryError) as error:
        print(error, file=sys.stderr)
        return INVALID_INPUT
    instructions = repository.reviewer_instructions(repo)
    if not instructions:
        neither = " nor ".join(repository.REVIEWER_INSTRUCTIONS)
        print(f"no {neither} in {repo}: the engine keeps its own rules", file=sys.stderr)
    rule = open_code_review.rule_file(instructions, engine.include, engine.exclude)
    print(json.dumps(rule, indent=2, ensure_ascii=False))
    return 0


def _review_pr(arguments):
    """Reviews the pull request as `relecteur eval` reviews a case, and writes the engine's output
    for `relecteur post-review`, which alone holds the token that posts it: the engine never
    shares a process with it."""
    try:
        repo = repository.root(Path.cwd())
        settings = config.load(repo / CONFIG)
        reviewer = settings.model
        model = Model.reviewer(reviewer.url, reviewer.name, reviewer.protocol, os.environ)
    except (InvalidConfig, MissingApiKey, repository.RepositoryError) as error:
        stdout, stderr = "", f"{error}\n"
    else:
        with _reached(model) as engine_model:
            stdout, stderr = open_code_review.pull_request_output(
                repo,
                arguments.base,
                arguments.head,
                engine_model,
                settings.engine,
                arguments.background,
                repository.reviewer_instructions(repo),
            )
    arguments.output.mkdir(parents=True, exist_ok=True)
    (arguments.output / "review.json").write_text(stdout, encoding="utf-8")
    (arguments.output / "review.log").write_text(stderr, encoding="utf-8")
    print(stderr, file=sys.stderr, end="")
    return 0


def _post_review(arguments):
    """Posts the review on its pull request, and fails when the reviewer, rather than the model,
    kept it from reviewing the pull request."""
    review = open_code_review.pull_request_review(
        _content(arguments.output / "review.json"), _content(arguments.output / "review.log")
    )
    pull_request = github.PullRequest(arguments.pr, os.environ)
    inline, elsewhere = github.placed(
        review.findings, pull_request.diff_lines(), pull_request.commented_lines()
    )
    pull_request.comment(arguments.head, inline)
    pull_request.summarize(github.summary_body(summary.text(review), elsewhere))
    _set_status(pull_request, arguments.head, review)
    print(summary.text(review))
    return 1 if review.failed else 0


def _set_status(pull_request, head, review):
    """Shows how the review ended among the checks of the pull request, when the workflow grants
    `statuses: write`: without it, the review goes on without a status."""
    run = (
        f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
        f"/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    )
    try:
        pull_request.set_status(head, *summary.commit_status(review), run)
    except urllib.error.HTTPError as error:
        print(
            f"no status on the commit (HTTP {error.code}): the workflow needs `statuses: write`",
            file=sys.stderr,
        )


def _content(path):
    return path.read_text(encoding="utf-8") if path and path.is_file() else ""


def _cases(paths):
    """The cases of the given files or directories, or of the repository's, with the repository
    they belong to and its environment."""
    paths = paths or [repository.cases_directory(Path.cwd())]
    cases = load_cases(*paths)
    repo = repository.root(paths[0]).resolve()
    return paths, cases, repo, repository.environment(repo, os.environ)


class InvalidReviews(Exception):
    pass


# Written next to the saved reviews: the model that made them, never its key.
_REVIEWER = "reviewer.json"


def _save_reviewer(model, directory):
    reviewer = {"url": model.url, "name": model.name}
    (directory / _REVIEWER).write_text(json.dumps(reviewer) + "\n", encoding="utf-8")


def _saved_reviewer(directory, environ):
    """The model that made the saved reviews, with the key the environment gives the reviewer."""
    path = directory / _REVIEWER
    if not path.is_file():
        raise InvalidReviews(
            f"{path} does not exist: save reviews with `relecteur eval --save-reviews`"
        )
    reviewer = json.loads(path.read_text(encoding="utf-8"))
    return Model(reviewer["url"], reviewer["name"], environ.get("RELECTEUR_API_KEY", ""))


def _report(cases, reviews, judge, threshold, arguments):
    report = evaluate(cases, reviews, DefectFinder(judge, arguments.line_tolerance, threshold))
    _print(report, reviews)
    return EXIT_CODES[report.outcome]


def _config(repo, arguments):
    """The repository's configuration, overridden by the options of the call.

    An option naming another endpoint or judge leaves out the protocol or the model configured
    for the one it replaces.
    """
    settings = config.load(repo / CONFIG)
    engine = replace(
        settings.engine,
        **{
            name: value
            for name in ("effort", "concurrency")
            if (value := getattr(arguments, name, None)) is not None
        },
    )
    model = settings.model
    if (url := getattr(arguments, "model_url", None)) and url != model.url:
        model = replace(model, url=url, protocol=None)
    if name := getattr(arguments, "model", None):
        model = replace(model, name=name)
    judge = settings.judge
    if arguments.judge and arguments.judge != judge.name:
        judge = replace(judge, name=arguments.judge, model=None)
    if arguments.judge_model:
        judge = replace(judge, model=arguments.judge_model)
    if arguments.judge_threshold is not None:
        judge = replace(judge, threshold=arguments.judge_threshold)
    return config.Config(engine, model, judge)


@contextmanager
def _reached(model):
    """The model as the engine reaches it: an OpenAI-compatible endpoint through the relay that
    has Albert call tools, Anthropic's API directly."""
    if model.protocol != "openai":
        yield model
        return
    with proxy.relaying(model.url) as relay_url:
        yield replace(model, url=relay_url)


def _judged_by(judge):
    model = judge.model or judges.DEFAULT_MODELS[judge.name]
    return f"{judge.name} ({model}), confirming a defect from a probability of {judge.threshold}"


def _describe(settings):
    budget = settings.max_tokens_budget
    return (
        f"effort {settings.effort}, {settings.concurrency} group(s) of files at once, "
        f"{f'at most {_token_count(budget)} tokens' if budget else 'no token budget'} per review, "
        f"findings in {settings.language or 'English'}"
    )


def _rules_followed(repo, instructions):
    if not instructions:
        return f"the engine's own rules, without {_joined(repository.REVIEWER_INSTRUCTIONS)}"
    present = [name for name in repository.REVIEWER_INSTRUCTIONS if (repo / name).is_file()]
    return f"rules of {_joined(present)}"


def _joined(names):
    return " and ".join(names) if len(names) < 3 else ", ".join(names[:-1]) + f" and {names[-1]}"


def _proxy(port, upstream):
    print(f"relaying http://127.0.0.1:{port} to {upstream}, until interrupted", flush=True)
    with suppress(KeyboardInterrupt):
        proxy.serve(upstream, port)
    return 0


def _review(case, repo, model, engine, instructions):
    print(f"reviewing {case.name} ({case.base[:10]}..{case.head[:10]})", file=sys.stderr)
    try:
        repository.ensure_commits(repo, case.base, case.head)
    except repository.RepositoryError as error:
        return Review(error=str(error))
    return open_code_review.review(
        repo, case.base, case.head, model, engine, case.pr and case.pr.text, instructions
    )


def _saved_review(path):
    if not path.is_file():
        return Review(error=f"no saved review at {path}")
    return load(path)


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


def _print(report, reviews):
    print()
    for result in report.results:
        summary = "; ".join(result.reasons) or (
            f"{len(result.findings)} finding(s), ceiling is {result.case.max_findings}"
        )
        review = reviews[result.case]
        cost = _cost(review.seconds, review.tokens)
        print(f"{result.outcome.name:<8} {result.case.name}{cost and f' ({cost})'}: {summary}")
        for finding in result.findings:
            text = finding.text.splitlines()[0] if finding.text else ""
            labels = "/".join(label for label in (finding.category, finding.severity) if label)
            location = f"{finding.path}:{finding.start_line}{labels and f' [{labels}]'}"
            print(f"         {location}: {text}")
        taken = {defect_result.finding for defect_result in result.defects if defect_result.found}
        for defect_result in result.defects:
            print(f"         {_defect_line(defect_result, taken)}")
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
    print(f"cost: {_total_cost([review for review in reviews.values() if review.seconds])}")
    print(f"verdict: {report.outcome.name}")


def _cost(seconds, tokens):
    parts = []
    if seconds is not None:
        minutes, seconds = divmod(round(seconds), 60)
        parts.append(f"{minutes}m{seconds:02d}s" if minutes else f"{seconds}s")
    if tokens is not None:
        parts.append(f"{_token_count(tokens)} tokens")
    return ", ".join(parts)


def _total_cost(reviews):
    if not reviews:
        return "unknown"
    seconds = sum(review.seconds for review in reviews)
    tokens = _sum(review.tokens for review in reviews)
    average = _cost(
        seconds / len(reviews), None if tokens is None else round(tokens / len(reviews))
    )
    return f"{_cost(seconds, tokens)} for {len(reviews)} review(s), {average} per review on average"


def _token_count(tokens):
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens / 1_000:.0f}k"
    return str(tokens)


def _sum(values):
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _defect_line(result, taken):
    """The defect, found or missed, and the finding the judge rated highest for it.

    `taken` are the findings that found a defect of the case: a finding finds one at most.
    """
    defect = result.defect
    status = "found" if result.found else "missed"
    escaped = ", which the human review let through" if defect.escaped_review else ""
    if result.finding is None:
        return f"{status} defect at {defect.location}{escaped}: no finding near it"
    elsewhere = (
        ", which found another defect" if not result.found and result.finding in taken else ""
    )
    return (
        f"{status} defect at {defect.location}{escaped}: the judge gives "
        f"{result.probability:.2f} to {result.finding.path}:{result.finding.start_line}{elsewhere}"
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
