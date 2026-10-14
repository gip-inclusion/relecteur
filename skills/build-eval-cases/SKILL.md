---
name: build-eval-cases
description: Draft relecteur evaluation cases from this repository's history, check them with the harness's validator, and hand them over uncommitted, with their evidence.
disable-model-invocation: true
---

# Build evaluation cases

relecteur evaluates an automated code reviewer by replaying past pull requests of a repository:
on a sound pull request the reviewer should stay silent, on a pull request that introduced a
defect it should flag it. Each replayed pull request is a **case**, a TOML file in the
repository's `.relecteur/cases` directory.

You draft cases from the history of the repository you are in, check them, and hand them,
uncommitted, to the maintainer who asked for them. The maintainer reviews them and adds those that
hold through a pull request, whose merge is what makes them count: your cases are **drafts**, and
each one carries the **evidence** (links to the pull request, its approval, the fix) that lets
the maintainer check it in minutes.

## Before you start

- **How many cases.** Draft the number the person asked for, or 5. Unless they asked for one
  kind, draft as many silence cases as defect cases, the odd one being a defect case. When the
  history yields fewer good cases than asked, deliver those and say so: a weak case costs the
  maintainer more than a missing one.
- **Which pull requests.** Start from the most recent and go back: recent pull requests match
  the code and the conventions the reviewer works with today. Keep each case under a few hundred
  changed lines in reviewable files: a replay reviews every file, and a large pull request costs
  minutes of model time and dilutes the reviewer's attention.
- **Tools.** git with the full history (`git rev-parse --is-shallow-repository` prints
  `false`), the `relecteur` and `ocr` (open-code-review) commands installed as relecteur's
  README describes, and read access to the GitHub API. `<owner>/<repo>` is the repository on
  GitHub. The API calls below use the GitHub CLI (`gh api`); any other access to the same REST
  endpoints works the same, such as an MCP server or curl with a token.
- **Commits.** The head of a squash-merged pull request, or any commit no local branch holds,
  needs `git fetch origin <sha>` before git can read it. In a script, write
  `"${head}:${path}"`: zsh reads `$head:a…` as a modifier.
- **Existing cases.** Read `.relecteur/cases/*.toml`: a pull request already named in a
  `pull_request` field is taken, and so is a fix whose pull request, or commit when it has
  none, is already linked in a `fix` field.

## The case format

A silence case is a pull request approved without any comment:

```toml
pull_request = "https://github.com/gip-inclusion/rdv-insertion/pull/3390"
notes = "Removes Sentry alerts from two jobs and updates their specs. Approved by the maintainer on 2026-09-29 without any comment: the reviewer should stay silent."
base = "b2f7f9a327f098f6ef64d91d13c193353d92ab5d"
head = "38ed0cb00af75b0fd9b533521af64be6dd397be0"
max_findings = 0

[pr]
title = "fix(sentry): stop sending business alerts to Sentry"
description = '''
## Contexte

`AlertMotifCategoryHasChangedJob` et `AlertUserAddedToAnotherDepartmentJob` envoyaient leur alerte métier à la fois sur Slack et dans Sentry.
'''
```

A defect case is a pull request that introduced a defect a later commit fixed. Listing
`expected_defects` is what makes it a defect case:

```toml
pull_request = "https://github.com/gip-inclusion/rdv-insertion/pull/3242"
notes = "Moves the check that a user has an identifier from a service into the User model. Approved by a teammate on 2026-03-12, then fixed by #3252 two days after the merge, because users imported from RDV-Solidarités could no longer be created: the reviewer should flag it."
base = "3cb0e646c8c743d276a320776cfeb367935511c0"
head = "ed3b4ef257fb4b9c63753bb2cfe3430cad1a2be8"
max_findings = 2

[[expected_defects]]
path = "app/models/user.rb"
line = 84
concept = "`validate :identifier_must_be_present` now runs on every save of a user, including users imported from RDV-Solidarités, who can have none of these identifiers: creating them fails."
fix = "https://github.com/gip-inclusion/rdv-insertion/pull/3252"
escaped_review = true
```

| Field | Meaning |
| --- | --- |
| `pull_request` | The pull request's `html_url`. |
| `notes` | For humans only, never shown to the reviewer: what the pull request does, the facts that make it a case (approval date, fix and delay), and what the reviewer should do. |
| `[pr]` | At the end of the file, the text of the pull request, which the reviewer reads as the author's intent, as it will in CI: `title` and `description` are the `title` and `body` that `pulls/<number>` returns, with `\r\n` turned into line breaks. Write `description` as a TOML literal multi-line string (`'''`), which keeps backslashes as they are, and leave it out when the body is empty. |
| `base`, `head` | Full SHAs of the code the human reviewer read: the pull request's `base.sha` and `head.sha` (`gh api repos/<owner>/<repo>/pulls/<number>`), except for a defect caught in review. |
| `max_findings` | `0` for a silence case; for a defect case, the number of expected defects plus one, which leaves room for one sound finding beside them. |
| `path`, `line` | The file and the line the reviewer would comment on, numbered as in the `head` commit. The harness matches findings within a few lines of it: when the defect shows in several places of the file, such as a function and the call that fails, list each of them (`line = [14, 28, 35]`). |
| `also_at` | Optional. Other files of the pull request where the defect shows, such as a caller the change breaks, each with its lines: `also_at = [{ path = "app/jobs/plan_job.rb", line = 2 }]`. |
| `concept` | The defect in plain words, which a judge compares with the reviewer's findings: see "Writing the concept". |
| `fix` | Link to the change that fixed the defect: its pull request (`https://github.com/<owner>/<repo>/pull/<number>`); its commit when it has none (`https://github.com/<owner>/<repo>/commit/<sha>`); for a defect caught in review, the fix commit within the pull request (`https://github.com/<owner>/<repo>/pull/<number>/commits/<sha>`). |
| `escaped_review` | `true` when the human review let the defect through to the merge, `false` when a human reviewer flagged it and it was fixed within the pull request. |

The format has one more field, `forbidden_remarks`, which the maintainer fills from the reviewer's
findings judged wrong during its calibration: history does not provide them, and your cases leave
it out.

Write `notes` and `concept` in the language of the existing cases, English when there are
none. Name the file `pr-<number>-<what-it-does>.toml`, in a few kebab-case English words. A pull
request with several defects is one case, with one `[[expected_defects]]` table per defect.

## Reading a review

Both kinds of case rest on what a human reviewer did, read from three endpoints:

```sh
gh api repos/<owner>/<repo>/pulls/<number>/reviews     # approvals, with their body and commit_id
gh api repos/<owner>/<repo>/pulls/<number>/comments    # comments on lines
gh api repos/<owner>/<repo>/issues/<number>/comments   # conversation
```

- **An approval** is a review by a human other than the author (a bot's `user.type` is `Bot` and
  its login ends in `[bot]`) whose `state` is `APPROVED`. It vouches for the code of its
  `commit_id`. A repository that dismisses approvals on a new push shows them as `DISMISSED`,
  like dismissed change requests: such a review is an approval when its `review_dismissed`
  event, in `gh api repos/<owner>/<repo>/issues/<number>/timeline`, has a `dismissed_review`
  whose `state` is `approved`.
- **A comment** is anything a human other than the author wrote: a review body beyond a bare
  acknowledgement ("LGTM", "Thanks 👍"), a comment on a line, a conversation comment. What bots
  write (CI, previews, coverage) does not count.
- The `comments` field of a search result or of `pulls/<number>` counts the conversation
  comments: at `0`, the third call has nothing to return.

## Silence cases

1. **List candidates**:

   ```sh
   gh api --method GET search/issues -f sort=created -f order=desc -f per_page=100 \
     -f q='repo:<owner>/<repo> is:pr is:merged review:approved -author:app/dependabot -author:app/renovate' \
     --jq '.items[] | "\(.number) \(.user.login) comments=\(.comments) \(.title)"'
   ```

   Keep only the number, author, comment count and title of each result: the full results run
   to hundreds of kilobytes. The search only narrows the field. Its `comments:0` qualifier also
   counts acknowledgements and drops sound pull requests: leave it out, and read each
   candidate's review instead.

2. **Keep the pull requests approved without any comment**: an approval whose `commit_id` is
   the pull request's `head.sha`, and no comment at all.

3. **Check that it stayed sound**: read the fix commits that touched its files after its merge
   (`git log --oneline <merge_commit_sha>..origin/<default branch> -- <files>`). A fix that
   corrects a line this pull request wrote makes it a defect case candidate instead.

4. **Read it as the reviewer would.** A pull request no fix touched can still hold a defect
   nobody has noticed yet. Read its diff and the code it relies on (the callers of what it
   changes, the types of the values it compares, the callbacks and scopes it triggers), looking
   for what "Defect cases" calls a defect, within what the reviewer is asked to report
   (`REVIEW.md` and `AGENTS.md`, when the repository has them). Check each suspicion: run the
   code when that is cheap (a console, a test), otherwise follow it through the code until it
   holds or falls. A defect you confirm rules the pull request out: give it in your report, with
   how you checked it, as a defect still on the default branch, which makes a defect case once it
   is fixed. A defect outside what the reviewer is asked to report leaves the case a silence
   case: mention it in your report.

5. **Prefer substance.** The best silence cases change logic a noisy reviewer would comment on;
   a typo fix or a version bump tests little. Spread the cases across areas of the code and
   authors.

## Defect cases

A defect case rests on a defect that existed and was fixed: wrong behaviour, or a breach of a
convention the repository has written down. It comes from one of two sources; draft mostly from
the first, which measures what the reviewer adds to the humans.

### A defect that escaped review

Tracing a fix back to the pull request that introduced the defect is the step agents get wrong
most often: verify each link with git or the API rather than infer it from commit messages.

1. **List fix commits** on the default branch. See first which subject prefixes the repository
   uses for fixes (`fix`, `bug`, `hotfix`…), then list them, filtering on the subject alone since
   `--grep` also matches message bodies:

   ```sh
   git log origin/<default branch> --no-merges --format='%s' | grep -oE '^[A-Za-z]+' | sort | uniq -c | sort -rn | head -20
   git log origin/<default branch> --no-merges --format='%H %ad %s' --date=short | grep -iE '^[0-9a-f]+ [0-9-]+ (<prefixes, such as fix|bug>)'
   ```

2. **Keep fixes of behaviour a reader could have caught.** Read the fix
   (`git show <fix commit>`) and its pull request
   (`gh api repos/<owner>/<repo>/commits/<fix commit>/pulls`); a fix pushed straight to the
   default branch has none, and the commit alone is its evidence. Keep it when it
   corrects wrong behaviour (a crash, a wrong result, lost data, a security hole) in reviewable
   code, and a careful reader of the faulty pull request and of the repository could have seen
   the defect. Move on from fixes of wording, styling, CI, configuration values, dependency
   versions or flaky tests, and from defects that only production data or a partner's behaviour
   revealed.

   The failure must be established, not guessed from the fix. When neither the fix's message,
   its pull request nor its tests state it, reproduce it if that is cheap (a test, a query);
   otherwise keep the case only with a note, in your report, that the defect is
   inferred from its fix, so that the maintainer decides.

3. **Find the faulty line** in the fix's parent: the line the fix changes or deletes or, when the
   fix only adds a guard, the line the guard protects.

4. **Find the change that made it wrong.**

   ```sh
   git blame -L <line>,<line> <fix commit>^ -- <path>
   git log -L <line>,<line>:<path> <fix commit>^    # the line's whole history
   ```

   Blame names the last commit that wrote the line, which is not always the one that made it
   wrong:
   - when that commit only moved, reformatted or renamed the line, go back through the line's
     history;
   - when the line was right when written, and a later change elsewhere broke it (a caller, a
     condition or a value it relies on), the faulty change is that later one: look for it in
     `git log <commit that wrote the line>..<fix commit>^ -- <related files>`. The defect's
     `path` and `line` then point into that change, where a human reviewer of its pull request
     would have seen it.

5. **Find its pull request**: `gh api repos/<owner>/<repo>/commits/<commit>/pulls` names it,
   including when the repository squash-merges and blame names the squash commit.

6. **Check the review** (see "Reading a review"). Keep the pull request only when an approval's
   `commit_id` already holds the faulty code (`git show <commit_id>:<path>` contains it): a pull
   request merged without human approval tells nothing about what review catches.
   `escaped_review` is `true` when no comment flagged the defect.

7. **Freeze it.** `fix` links to the fix's pull request, or to the fix commit when it has none,
   and `line` is the number of the faulty line in `git show <head>:<path>`, which often differs
   from its number in the fix's parent.

### A defect or a convention caught in review

A human reviewer's comment on a line pointed out a defect, or asked for what a convention written
in the repository prescribes (in its `AGENTS.md`, `CONTRIBUTING.md` or the like), and the author
changed the code accordingly in a later commit of the same pull request. Keep only comments that
wrong behaviour or a written convention backs, and judge that from the code, not from how the
comment is worded: a question or a suggested simplification points out a defect when the code
before it gives a wrong result in a situation that can occur, which you check as a suspicion in a
silence case. A remark of taste, on naming or design, or one its author labelled minor
("nitpick", "nit", "if you want"), is one the reviewer is not expected to make.

1. Among reviewed pull requests, read the comments on lines (`pulls/<number>/comments`) for one
   that points out wrong behaviour or asks for what a written convention prescribes, followed by
   a commit of the pull request (`gh api repos/<owner>/<repo>/pulls/<number>/commits`) that
   changes the commented lines as asked. A comment whose `line` is `null` sits on code a later
   commit changed: those comments are where to look first.
2. Freeze the code the human reviewer read, before the fix: `head` is the comment's
   `original_commit_id`, `base` the pull request's `base.sha`, `path` and `line` the comment's
   `path` and `original_line`, `fix` the link to the commit that corrected it, and
   `escaped_review` is `false`.
3. Move on when `git fetch origin <head>` fails: a force-push can have erased the commits a
   pull request had before.

### Writing the concept

A judge reads one of the reviewer's findings and the concept, and answers whether they describe
the same defect. Write the defect as it shows at `head`: what goes wrong, in which situation, and
through which code, in one or two sentences that name the function or condition involved. The
concept of the defect case above is the target: it describes the defect, and leaves how it was
fixed to the change `fix` links to. For a convention, the concept names the rule and how the code
breaks it: "The partial reads @organisation and @category_configuration instead of receiving them
as locals, against the convention that ERB partials receive their data through locals passed to
render."

## Check every case

Write the files in `.relecteur/cases`, then check them. A case that fails a check is corrected or
deleted: only cases that pass every check are handed over.

1. `relecteur validate` prints `<N> valid case(s)`, `<N>` counting the existing cases and yours;
   otherwise it names each file and its problem.
2. For each of your cases:
   - `base`, `head` and each fix commit exist: `git cat-file -e <sha>^{commit}`, once fetched;
   - each `fix` link leads to its fix commit: to the pull request that
     `gh api repos/<owner>/<repo>/commits/<fix commit>/pulls` names, or to the commit itself;
   - `git show <head>:<path> | sed -n '<line>p'` prints the faulty line of each expected defect;
   - `ocr delegate preview --from <base> --to <head>` lists the `path` of each expected defect
     among the reviewable files, and at least one reviewable file for a silence case: on files
     the engine skips, a replay tests nothing. The `merge_base` it shows can differ from `base`
     when the base branch had moved on: the harness, too, reviews the head against that merge
     base.

Checking stops there: replaying the cases with `relecteur eval` calls a model, and that run is the
maintainer's to start.

## Hand the cases over

1. Leave your case files uncommitted in `.relecteur/cases`: you commit and push nothing.
2. Hand back a report the maintainer can check each case with, without searching, and reuse as
   the description of that pull request, following the repository's conventions for one. For
   each case, give its file and its evidence:
   - a silence case: the pull request and its approval;
   - a defect case: the pull request, its approval, the faulty line at head
     (`https://github.com/<owner>/<repo>/blob/<head>/<path>#L<line>`), the fix, and whether the
     defect is inferred from its fix.
3. End the report with the number of cases of each kind, the defects still on the default branch
   that reading the silence cases found, and, if you drafted fewer than asked, why.
