import subprocess
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values

CASES = Path(".relecteur", "cases")


class RepositoryError(Exception):
    pass


def root(path: Path) -> Path:
    completed = _git(path if path.is_dir() else path.parent, "rev-parse", "--show-toplevel")
    if completed.returncode != 0:
        raise RepositoryError(f"{path} is not inside a git repository")
    return Path(completed.stdout.strip())


def cases_directory(path: Path) -> Path:
    cases = root(path) / CASES
    if not cases.is_dir():
        raise RepositoryError(f"{cases} does not exist: create it, with one file per case")
    return cases


def environment(repo: Path, environ: Mapping[str, str]) -> dict[str, str]:
    """The environment, completed by the variables of the repository's .env file.

    As with dotenv, a variable the environment already sets keeps its value.
    """
    values = dotenv_values(repo / ".env")
    return {**{name: value for name, value in values.items() if value is not None}, **environ}


def ensure_commits(repo: Path, *commits: str) -> None:
    """Makes the commits available locally, fetching them from origin when no branch holds them."""
    missing = [commit for commit in commits if not _present(repo, commit)]
    if missing:
        _git(repo, "fetch", "--quiet", "--no-tags", "origin", *missing)
        missing = [commit for commit in missing if not _present(repo, commit)]
    if missing:
        raise RepositoryError(
            f"commit(s) {', '.join(missing)} neither in {repo} nor fetchable from its origin remote"
        )


def _present(repo, commit):
    return _git(repo, "cat-file", "-e", f"{commit}^{{commit}}").returncode == 0


def _git(repo, *arguments):
    return subprocess.run(
        ["git", "-C", str(repo), *arguments], capture_output=True, text=True, check=False
    )
