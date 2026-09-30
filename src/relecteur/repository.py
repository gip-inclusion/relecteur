import subprocess
from pathlib import Path


class RepositoryError(Exception):
    pass


def root(path: Path) -> Path:
    """The root of the git repository holding `path`."""
    completed = _git(path if path.is_dir() else path.parent, "rev-parse", "--show-toplevel")
    if completed.returncode != 0:
        raise RepositoryError(f"{path} is not inside a git repository: pass --repo")
    return Path(completed.stdout.strip())


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


def _present(repo: Path, commit: str) -> bool:
    return _git(repo, "cat-file", "-e", f"{commit}^{{commit}}").returncode == 0


def _git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments], capture_output=True, text=True, check=False
    )
