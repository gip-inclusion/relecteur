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
- The open-code-review CLI, version 1.12.11, which provides the `ocr` command:

  ```sh
  npm install --global @alibaba-group/open-code-review@1.12.11
  ```

- An API key for the model endpoint, in `RELECTEUR_API_KEY`. The default model is served by
  [Albert](https://albert.api.etalab.gouv.fr): create the key from an Albert account,
  preferably one attached to a service address rather than to a person.
- To judge expected defects with Jev rather than Albert, an API key from
  [TypeSafe](https://typesafe.ai) in `TYPESAFE_API_KEY`.

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
description = "Applies the discount before the total. Approved without any comment: the reviewer should stay silent."
base = "b2f7f9a327f098f6ef64d91d13c193353d92ab5d"
head = "38ed0cb00af75b0fd9b533521af64be6dd397be0"
max_findings = 0

[[forbidden_remarks]]
path = "src/billing.py"
line = 42
concept = "Asks to rename `total` although the name matches the invoice vocabulary."
```

| Field | Meaning |
| --- | --- |
| `pull_request` | Link or identifier of the pull request, for the humans reading the case. |
| `description` | What the reviewer is expected to do, and why. Read by humans only: it is never shown to the reviewer. |
| `base`, `head` | Full SHAs of the pull request's base and head commits. |
| `max_findings` | The case fails as soon as the reviewer makes more findings than this. |
| `forbidden_remarks` | Optional. Remarks the reviewer must not make again: a finding covering `line` of `path` fails the case, whatever `max_findings` allows. |
| `expected_defects` | Optional. Defects the reviewer should flag, which makes the case a defect case: see below. |

A defect case is sourced in a fix commit, and describes each defect in plain words:

```toml
pull_request = "https://github.com/team/app/pull/1234"
description = "Applies the discount twice, fixed by #1240 the day after the merge: the reviewer should flag it."
base = "b2f7f9a327f098f6ef64d91d13c193353d92ab5d"
head = "38ed0cb00af75b0fd9b533521af64be6dd397be0"
max_findings = 2

[[expected_defects]]
path = "src/billing.py"
line = 42
concept = "Applies the discount a second time when the invoice total is recomputed."
fix = "02e2ac918dae906395d05b502d386fcb4bfe20a8"
escaped_review = true
```

| Field | Meaning |
| --- | --- |
| `path`, `line` | Where the defect is, in the pull request's head commit. |
| `concept` | The defect, in plain words: the judge compares it with the text of the findings. |
| `fix` | Full SHA of the commit that fixed the defect. |
| `escaped_review` | Whether the human review of the pull request let the defect through, so that the report tells what the reviewer adds to the humans rather than how much it resembles them. |

`max_findings` must leave room for every expected defect.

A case can be written by hand or drafted by an agent. Either way it counts once it is merged:
add cases through a pull request, whose review is where a human vouches for them.

The harness replays a pull request from its recorded commits, with git alone, whatever
the current state of branches: when a commit is missing locally, as with the head of a
squash-merged pull request, it is fetched from the `origin` remote.

## Usage

Run from anywhere inside the evaluated repository:

```sh
relecteur validate      # check the format of every case in .relecteur/cases
relecteur eval          # review every case of .relecteur/cases and give a verdict
```

Both commands read `.relecteur/cases` at the root of the repository by default, and stop with
an explicit message when it does not exist. Pass a case file or directory to use another one:
`relecteur eval .relecteur/cases/pr-1234.toml` replays a single case.

`validate` exits with 1 when a case is invalid, naming each file and its problem. `eval`
exits with:

| Code | Meaning |
| --- | --- |
| 0 | Every silence case passed. |
| 1 | At least one silence case failed: the reviewer made too many remarks, repeated a forbidden one, or did not finish its review. |
| 2 | Invalid input: a malformed case, a missing API key, an invalid option, no repository found. |
| 3 | No verdict: no silence case failed, but one could not be reviewed: model unavailable (overload, quota reached, timeout), engine missing, or a pull request with no file the engine reviews. |

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
the probability that the finding describes the defect, which is found from a threshold on.

| Option | Default | |
| --- | --- | --- |
| `--judge` | `albert` | `albert` asks a model of Albert; `jev` asks [Jev](https://typesafe.ai), TypeSafe's judgment model. |
| `--judge-model` | `deepseek-v4-flash-0731` for `albert`, `jev-latest` for `jev` | |
| `--judge-threshold` | `0.5` | Probability from which a defect is found. |
| `--line-tolerance` | `5` | Lines between a finding and a defect for the judge to be asked. |

The `albert` judge asks for a one-word answer, yes or no, and reads the probability of yes in
the logprobs of that word. It asks Albert whatever model reviews, so that reviewers are compared
under the same judge: its API key is `RELECTEUR_JUDGE_API_KEY`, or `RELECTEUR_API_KEY` when
Albert serves the reviewer too. The `jev` judge's
request follows TypeSafe's System One API as RubyLLM implements it; it has not been run yet.

A judge that cannot answer, model unavailable or answer unreadable, makes the case an error,
never a missed defect.

## Model

open-code-review reaches the model through an OpenAI-compatible endpoint. The model is
configured, never written in code: each setting is read from the command line, then the
environment, then falls back to Albert.

| Option | Environment variable | Default |
| --- | --- | --- |
| `--model-url` | `RELECTEUR_MODEL_URL` | `https://albert.api.etalab.gouv.fr/v1` |
| `--model` | `RELECTEUR_MODEL` | `deepseek-v4-flash-0731` |
| | `RELECTEUR_API_KEY` | none, required |
| | `RELECTEUR_JUDGE_API_KEY` | `RELECTEUR_API_KEY` when the reviewer is served by Albert; an Albert key otherwise, for the `albert` judge |

The engine runs with an empty home directory, so that a personal open-code-review
configuration never overrides the model chosen here; git keeps the global configuration of
the real home directory.

### Tool calls on Albert

The engine works by having the model call its tools (read a file, search the code, post a
remark). Albert's gateway up to version 0.8.0 turns a request that does not set `tool_choice`
into `tool_choice: "none"`, against the OpenAI convention the engine relies on: DeepSeek then
never calls a tool, and every review runs out of rounds. Albert 0.9.0 fixes it, with a deployment
announced for 2026-10-19 ([changelog](https://guides.ia.numerique.gouv.fr/albert-api/ressources/changelog)).

Until then, `relecteur eval` sends the engine's requests through a local relay that adds
`tool_choice: "auto"` to the requests carrying tools, and forwards everything else unchanged.
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
case loader, the engine adapter, against engine outputs recorded or written from its source, the
`albert` judge's reading of answers, recorded or built for an edge case, and the relay's rule for `tool_choice`. Running
git, the engine, the judges and the relay itself is checked by real runs.
