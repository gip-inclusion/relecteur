"""Posts a review in CI on its pull request, through GitHub's REST API: the findings on the lines
of the diff they concern, and a summary that each review of the pull request updates.

It comments only: it neither approves a pull request nor requests changes.
"""

import json
import re
import urllib.request
from collections.abc import Iterable, Mapping

from relecteur.review import Finding

# Marks the summary that each review of the pull request updates, and the findings it posted,
# for a review called again to leave out a finding on lines it already commented.
SUMMARY_MARKER = "<!-- relecteur -->"
_FINDING_MARKER = "<!-- relecteur finding -->"
_HUNK = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def lines_in_patch(patch: str) -> set[int]:
    """The lines of the new file that a patch shows, added or kept as context: those a review
    comment may target."""
    lines, line = set(), 0
    for text in patch.splitlines():
        if hunk := _HUNK.match(text):
            line = int(hunk[1])
        elif text.startswith(("+", " ")):
            lines.add(line)
            line += 1
    return lines


def placed(
    findings: Iterable[Finding],
    diff_lines: Mapping[str, set[int]],
    commented: Mapping[str, list[range]],
) -> tuple[list[Finding], list[Finding]]:
    """The findings to comment on their lines, and those the summary lists instead, whose lines
    are not all in the diff. A finding on lines already commented by the reviewer is left out."""
    inline, elsewhere = [], []
    for finding in findings:
        lines = range(finding.start_line, finding.end_line + 1)
        if any(set(lines) & set(done) for done in commented.get(finding.path, [])):
            continue
        if set(lines) <= diff_lines.get(finding.path, set()):
            inline.append(finding)
        else:
            elsewhere.append(finding)
    return inline, elsewhere


def summary_body(headline: str, elsewhere: list[Finding]) -> str:
    """The summary: how the review ended, then the findings it could not post on their lines."""
    body = f"{SUMMARY_MARKER}\n{headline}"
    if elsewhere:
        body += "\n\nRemarques sur des lignes que cette PR ne modifie pas :"
        for finding in elsewhere:
            body += f"\n\n**`{finding.path}`, {_lines(finding)}**\n\n{finding.text}"
    return body


class PullRequest:
    """A pull request of the repository the workflow runs on, read and commented with its token."""

    def __init__(self, number: int, environ: Mapping[str, str]):
        api = environ.get("GITHUB_API_URL", "https://api.github.com")
        self._repository = f"{api}/repos/{environ['GITHUB_REPOSITORY']}"
        self._token = environ["GITHUB_TOKEN"]
        self.number = number

    def diff_lines(self) -> dict[str, set[int]]:
        """The lines of each changed file that a review comment may target."""
        return {
            file["filename"]: lines_in_patch(file.get("patch", ""))
            for file in self._pages(f"/pulls/{self.number}/files")
        }

    def commented_lines(self) -> dict[str, list[range]]:
        """The lines of each file that the reviewer's comments still target."""
        commented: dict[str, list[range]] = {}
        for comment in self._pages(f"/pulls/{self.number}/comments"):
            if _FINDING_MARKER in comment["body"] and comment["line"]:
                start = comment["start_line"] or comment["line"]
                commented.setdefault(comment["path"], []).append(range(start, comment["line"] + 1))
        return commented

    def comment(self, head: str, findings: list[Finding]) -> None:
        """Posts the findings on their lines of `head`, in one review that blocks nothing."""
        if findings:
            self._request(
                "POST",
                f"/pulls/{self.number}/reviews",
                {
                    "commit_id": head,
                    "event": "COMMENT",
                    "body": "",
                    "comments": [_review_comment(finding) for finding in findings],
                },
            )

    def summarize(self, body: str) -> None:
        """Updates the summary of the pull request, or posts it on its first review."""
        summaries = [
            comment
            for comment in self._pages(f"/issues/{self.number}/comments")
            if SUMMARY_MARKER in comment["body"]
        ]
        if summaries:
            self._request("PATCH", f"/issues/comments/{summaries[-1]['id']}", {"body": body})
        else:
            self._request("POST", f"/issues/{self.number}/comments", {"body": body})

    def _pages(self, path):
        items, page = [], 1
        while batch := self._request("GET", f"{path}?per_page=100&page={page}"):
            items += batch
            page += 1
        return items

    def _request(self, method, path, body=None):
        request = urllib.request.Request(
            self._repository + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method=method,
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read() or "null")


def _review_comment(finding):
    comment = {
        "path": finding.path,
        "line": finding.end_line,
        "side": "RIGHT",
        "body": f"{finding.text}\n\n{_FINDING_MARKER}",
    }
    if finding.start_line < finding.end_line:
        comment |= {"start_line": finding.start_line, "start_side": "RIGHT"}
    return comment


def _lines(finding):
    if finding.start_line == finding.end_line:
        return f"ligne {finding.end_line}"
    return f"lignes {finding.start_line} à {finding.end_line}"
