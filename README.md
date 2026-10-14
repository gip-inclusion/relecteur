# relecteur

Evaluation harness for an automated code reviewer. It replays past pull requests of a
repository through [open-code-review](https://github.com/alibaba/open-code-review), and tells
whether the reviewer behaved as each case expects: on a pull request the maintainer approved
without a single comment, the reviewer is expected to stay silent; on a pull request that a later
commit had to fix, it is expected to flag the defect.

The package assumes nothing about the language, framework or domain of the repository it
evaluates: that repository only provides case files.

## Prerequisites

- Python 3.11 or later, and git 2.41 or later (open-code-review relies on its recent options).
- The open-code-review CLI, version 1.12.13, which provides the `ocr` command:

  ```sh
  npm install --global @alibaba-group/open-code-review@1.12.13
  ```

- The API key of the reviewer's endpoint, in `RELECTEUR_API_KEY`. The default model is served by
  [Albert](https://albert.api.etalab.gouv.fr): create the key from an Albert account,
  preferably one attached to a service address rather than to a person.
- The API key of the judge, in `RELECTEUR_JUDGE_API_KEY`: an Albert key for the `albert` judge,
  which can go without it when Albert serves the reviewer too, or a [TypeSafe](https://typesafe.ai)
  key for the `jev` judge.

These variables can also be set in the `.env` file at the root of the evaluated repository, which
`relecteur eval` reads as dotenv does: a variable the environment already sets keeps its value.
Keep that file out of git. The keys are the only settings read from the environment: the model
and the judge are chosen in the repository's configuration file (see "Configuration").

## Installation

Install the `relecteur` command once, in its own environment, with
[pipx](https://pipx.pypa.io) (`brew install pipx` on macOS). While the package is not
published, install it from a local checkout:

```sh
pipx install --editable ../relecteur
```

In a CI job, where the runner's Python is disposable, `pip install` does the same.

## Cases

A case is a TOML file describing a past pull request, frozen by its base and head commits.
The cases of a repository live in its `.relecteur/cases` directory, one file per case; the
file name is the case name.

A case that lists expected defects is a defect case: a pull request a later commit had to
fix, on which the reviewer is expected to flag each defect. Any other case is a silence case: a
pull request the maintainer approved without a single comment, on which the reviewer is
expected to stay silent.

```toml
pull_request = "https://github.com/team/app/pull/1234"
notes = "Applies the discount before the total. Approved without any comment: the reviewer should stay silent."
base = "b2f7f9a327f098f6ef64d91d13c193353d92ab5d"
head = "38ed0cb00af75b0fd9b533521af64be6dd397be0"
max_findings = 0

[[forbidden_remarks]]
path = "src/billing.py"
line = 42
concept = "Asks to rename `total` although the name matches the invoice vocabulary."

[pr]
title = "Apply the discount before the total"
description = '''
The discount applied to the total with taxes, against the terms of sale.
'''
```

| Field | Meaning |
| --- | --- |
| `pull_request` | Link or identifier of the pull request, for the humans reading the case. |
| `notes` | What the reviewer is expected to do, and why. Read by humans only: it is never shown to the reviewer. |
| `base`, `head` | Full SHAs of the code a human reviewed: the pull request's base and head commits, or, for a defect a reviewer caught, the commit they commented on as `head`. |
| `max_findings` | The case fails as soon as the reviewer makes more findings than this. |
| `forbidden_remarks` | Optional. Remarks the reviewer must not make again, taken from its findings the maintainer judged wrong: a finding covering `line` of `path` fails the case, whatever `max_findings` allows. |
| `expected_defects` | Optional. Defects the reviewer should flag, which makes the case a defect case: see below. |
| `pr` | Optional, at the end of the file. The `title` and `description` of the pull request, as its author wrote them: the reviewer reads them as the intent of the change, as it will in CI. |

A defect case is sourced in a fix commit, and describes each defect in plain words:

```toml
pull_request = "https://github.com/team/app/pull/1234"
notes = "Applies the discount twice, fixed by #1240 the day after the merge: the reviewer should flag it."
base = "b2f7f9a327f098f6ef64d91d13c193353d92ab5d"
head = "38ed0cb00af75b0fd9b533521af64be6dd397be0"
max_findings = 2

[[expected_defects]]
path = "src/billing.py"
line = 42
concept = "Applies the discount a second time when the invoice total is recomputed."
fix = "https://github.com/team/app/pull/1240"
escaped_review = true
```

| Field | Meaning |
| --- | --- |
| `path`, `line` | Where the defect is, in the `head` commit: a line, or a list of lines (`line = [28, 35]`) when a reviewer may point it out in several places, such as a function and its call. |
| `also_at` | Optional. Other files where a reviewer may point the defect out, each with its lines: `also_at = [{ path = "src/invoice.py", line = 7 }]`. |
| `concept` | The defect, in plain words: the judge compares it with the text of the findings. |
| `fix` | Link to the change that fixed the defect, for the humans reading the case: its pull request, its commit when it has none, or, for a defect a reviewer caught, the fix commit within the pull request. |
| `escaped_review` | Whether the human review of the pull request let the defect through, so that the report tells what the reviewer adds to the humans rather than how much it resembles them. |

`max_findings` must leave room for every expected defect.

A case can be written by hand or drafted by an agent, with the skill below. Either way it counts
once it is merged: add cases through a pull request, whose review is where a human vouches for
them.

The harness replays a pull request from its recorded commits, with git alone, whatever
the current state of branches: when a commit is missing locally, as with the head of a
squash-merged pull request, it is fetched from the `origin` remote.

### Drafting cases with an agent

[`skills/build-eval-cases/SKILL.md`](skills/build-eval-cases/SKILL.md) has an agent draft cases
from the history of a repository on GitHub: silence cases from pull requests approved without any
comment, defect cases from fix commits and from review comments the author acted on, about a
defect or a written convention. The agent checks its cases with `relecteur validate`,
and leaves them uncommitted with the evidence for each one: the person who ran it reviews them,
keeps those that hold, and adds them through a pull request.

A skill is a Markdown file, which any agent can follow. With Claude Code, copy the
`build-eval-cases` folder into the repository's `.claude/skills` directory, then run
`/build-eval-cases`, followed by the number of cases to draft (5 by default). With another agent,
ask it to read the file and follow it.

## Usage

Run from anywhere inside the evaluated repository:

```sh
relecteur validate      # check the format of every case in .relecteur/cases
relecteur eval          # review every case of .relecteur/cases and give a verdict
```

Both commands read `.relecteur/cases` at the root of the repository by default, and stop with
an explicit message when it does not exist. Pass case files or directories to use others:
`relecteur eval .relecteur/cases/pr-1234.toml` replays a single case.

Reviews vary from one run to the next, and a run takes long: `--save-reviews DIR` writes each
review to `DIR/<case>.json` as soon as it ends, and the model that made them to
`DIR/reviewer.json`; `relecteur score DIR` judges them again, with another judge or threshold,
without reviewing anew. A case without a saved review is an error.

```sh
relecteur eval --save-reviews runs/1     # review, and keep the reviews
relecteur score runs/1 --judge jev       # judge the same reviews again
```

`validate` exits with 1 when a case is invalid, naming each file and its problem. `eval`
exits with:

| Code | Meaning |
| --- | --- |
| 0 | Every silence case passed. |
| 1 | At least one silence case failed: the reviewer made too many remarks, repeated a forbidden one, or did not finish its review. |
| 2 | Invalid input: a malformed case, a missing API key, an invalid option, no repository found. |
| 3 | No verdict: no silence case failed, but one could not be reviewed: model unavailable (overload, quota reached, timeout), engine missing, or a pull request with no file the engine reviews. |

Each case's line tells how long its review took, pauses included, and the tokens the model
consumed, and the report ends with their total and their average per review.

Only silence cases decide the verdict: a remark on a sound pull request is a regression of the
reviewer, a missed defect is not. Defect cases are reported, with the defects found and among
them those the human review had let through, and never change the exit code.

A review that did not cover every file of the pull request is never scored on its findings.
When the model or the engine was out of reach, it is an error and no verdict. When the reviewer
was reached but did not finish, for instance by running out of rounds, the case fails: a broken
reviewer setup must not hide behind "no verdict". A pull request with no file the engine
reviews tests nothing, and gives no verdict either.

## Judge

A finding is matched to an expected defect in two steps. First, it must be in the defect's file,
within a few lines of it; a finding anywhere else never reaches the judge. Then the judge tells
the probability that the finding describes the defect, which is found from a threshold on. A
finding finds one defect at most, the one the judge is the most confident it describes: a remark
on one defect never counts for a neighbouring one.

The judge is chosen in the `[judge]` table of the configuration file (see "Configuration"), which
these options of `relecteur eval` and `relecteur score` override:

| Setting | Option | Default | |
| --- | --- | --- | --- |
| `name` | `--judge` | `albert` | `albert` asks a model of Albert; `jev` asks [Jev](https://typesafe.ai), TypeSafe's judgment model. |
| `model` | `--judge-model` | `deepseek-v4-flash-0731` for `albert`, `jev-latest` for `jev` | |
| `threshold` | `--judge-threshold` | `0.5` | Probability from which a defect is found. |
| | `--line-tolerance` | `5` | Lines between a finding and a defect for the judge to be asked. |

The judge's API key is `RELECTEUR_JUDGE_API_KEY`. The `albert` judge asks for a one-word answer,
yes or no, and reads the probability of yes in the logprobs of that word. It asks Albert whatever
model reviews, so that reviewers are compared under the same judge; when Albert serves the
reviewer too, the reviewer's key serves the judge. The `jev` judge's request follows TypeSafe's
System One API as RubyLLM implements it.

A judge that cannot answer, model unavailable or answer unreadable, makes the case an error,
never a missed defect.

## Model

open-code-review reaches the model through an OpenAI-compatible endpoint, such as Albert's, or
through Anthropic's API. The model is chosen in the `[model]` table of the configuration file
(see "Configuration"), which these options of `relecteur eval` override:

| Setting | Option | Default | |
| --- | --- | --- | --- |
| `url` | `--model-url` | `https://albert.api.etalab.gouv.fr/v1` | The endpoint; Anthropic's is `https://api.anthropic.com`, without `/v1`. |
| `name` | `--model` | `deepseek-v4-flash-0731` | |
| `protocol` | | `anthropic` for `api.anthropic.com`, `openai` otherwise | `openai` or `anthropic`, for an endpoint the URL does not tell, such as a gateway. |

Its API key is `RELECTEUR_API_KEY`. A `--model-url` naming another endpoint than the configured
one leaves out the configured protocol.

```toml
[model]
url = "https://api.anthropic.com"
name = "claude-opus-5-5"
```

The engine runs with an empty home directory, so that a personal open-code-review
configuration never overrides the model chosen here; git keeps the global configuration of
the real home directory.

### Reviewer instructions

The reviewer follows the repository's `REVIEW.md`, how to review, then its `AGENTS.md`, the
code conventions, as they are in the working tree: today's instructions are evaluated on past
pull requests. The engine applies one rule per file, so `relecteur eval` combines the two files
into a single rule on every file. The rule joins the engine's own rule for Python files, and
replaces it elsewhere: the engine's rules for a few file types (Maven, Gradle, package.json…),
and the default rule every other file gets, which leads the reviewer to remarks on naming and
test coverage. With one of the two files, the rule is that file; with neither, the engine
reviews by its own rules.

`relecteur rule` prints that rule, in the engine's format, for CI to pass the same one to the
engine; with neither file, it prints an empty rule, under which the engine keeps its own. The
files the engine reviews are chosen by the repository's
`.opencodereview/rule.json` (its `include` and `exclude` patterns), which the engine reads by
itself.

### Configuration

The repository's `.relecteur/config.toml` sets what an evaluation measures: the engine and the
model that review, for `relecteur eval` and, through it, for CI, and the judge. It holds no
secret, and is versioned with the cases, so that a score always tells which reviewer and which
judge made it. The options of `relecteur eval` and `relecteur score` override it, for a one-off
run.

```toml
effort = "high"
concurrency = 2
max_tokens_budget = 2000000
language = "French"

[model]
url = "https://albert.api.etalab.gouv.fr/v1"
name = "deepseek-v4-flash-0731"

[judge]
name = "jev"
threshold = 0.5
```

The model and the judge are described above; the engine settings sit at the top of the file:

| Setting | Option | Default | |
| --- | --- | --- | --- |
| `effort` | `--effort` | `high` | The engine's effort preset, `low`, `medium` or `high`: a higher one spends more rounds and tokens on each group of files. |
| `concurrency` | `--concurrency` | `2` | Groups of files the engine reviews at once. |
| `max_tokens_budget` | | none | Tokens a review may spend; the engine stops reviewing further files beyond it, and the review counts as not finished. |
| `language` | | English | The language of the findings. |

Each group sends its own requests to the model. Albert answers too many of them at once with
HTTP 429, hence 2 groups at a time by default, which a model served without such limits can
raise. At high effort, each request carries the whole conversation of its group: on Albert, the
largest pull requests only finish with 1 group at a time, which costs little time since the
per-minute limit is what slows a review down. The engine retries a refused request, then gives up on its files, as it does on files
that take longer than its timeout. When the rate limit or timeouts alone left files unreviewed,
`relecteur eval` resumes the engine's session after 1, then 2, then 4 minutes, and the engine
reviews the files left only. A case still incomplete afterwards gets no verdict.

### Tool calls on Albert

The engine works by having the model call its tools (read a file, search the code, post a
remark). Albert's gateway up to version 0.8.0 turns a request that does not set `tool_choice`
into `tool_choice: "none"`, against the OpenAI convention the engine relies on: DeepSeek then
never calls a tool, and every review runs out of rounds. Albert 0.9.0 fixes it, with a deployment
announced for 2026-10-19 ([changelog](https://guides.ia.numerique.gouv.fr/albert-api/ressources/changelog)).

Until then, `relecteur eval` sends the engine's requests to an OpenAI-compatible endpoint through
a local relay that adds `tool_choice: "auto"` to the requests carrying tools, and forwards
everything else unchanged; it reaches Anthropic's API directly.
To run the engine directly, start the relay and point the engine to it:

```sh
relecteur proxy --port 8765        # in another terminal
OCR_LLM_URL=http://127.0.0.1:8765 OCR_LLM_TOKEN=$RELECTEUR_API_KEY \
OCR_LLM_MODEL=deepseek-v4-flash-0731 OCR_LLM_PROTOCOL=openai \
ocr review --from <base> --to <head>
```

Remove the relay once Albert serves the fixed gateway.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install --editable '.[dev]'
.venv/bin/pytest
.venv/bin/mypy
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

The test suite needs no application repository, no network access and no model: tests
that try to open a connection fail. The tests cover the scorer, with a deterministic judge, the
case loader, the configuration file, the choice of the model's protocol and of the judges' keys,
the combination of the reviewer instructions, saved
reviews, the engine adapter, against engine outputs recorded or written from its source, the
`albert` judge's reading of answers, recorded or built for an edge case, and the relay's rule
for `tool_choice`. Running git, the engine, the judges and the relay itself is checked by real
runs.
