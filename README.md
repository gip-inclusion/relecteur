# relecteur

Evaluation harness for an automated code reviewer. It replays past pull requests of a
repository through [open-code-review](https://github.com/alibaba/open-code-review), and tells
whether the reviewer behaved as each case expects: on a pull request the maintainer approved
without a single comment, the reviewer is expected to stay silent.

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

Today every case is a silence case: a pull request the maintainer approved without a single
comment, on which the reviewer is expected to stay silent.

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
| 0 | Every case passed. |
| 1 | At least one case failed. |
| 2 | Invalid input: a malformed case, a missing API key, no repository found. |
| 3 | No verdict: no case failed, but the model or the engine could not review a case (overload, quota reached, engine missing). |

An unavailable model is never a verdict: a review that did not cover every file of the pull
request is reported as an error, not scored.

## Model

open-code-review reaches the model through an OpenAI-compatible endpoint. The model is
configured, never written in code: each setting is read from the command line, then the
environment, then falls back to Albert.

| Option | Environment variable | Default |
| --- | --- | --- |
| `--model-url` | `RELECTEUR_MODEL_URL` | `https://albert.api.etalab.gouv.fr/v1` |
| `--model` | `RELECTEUR_MODEL` | `deepseek-v4-flash-0731` |
| | `RELECTEUR_API_KEY` | none, required |

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
that try to open a connection fail. Only the scorer, the case loader and the engine adapter
are tested, the adapter against frozen engine outputs.
