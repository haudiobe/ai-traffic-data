"""Guards that keep source documents and generated outputs out of the repo."""
from __future__ import annotations

import subprocess
from pathlib import Path

FORBIDDEN_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".docx", ".doc", ".pptx", ".pdf", ".zip"}

REPO_ROOT = Path(__file__).resolve().parent.parent


def is_inside(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def assert_outside_repo(*paths: Path, repo_root: Path = REPO_ROOT) -> None:
    for p in paths:
        if p is not None and is_inside(p, repo_root):
            raise ValueError(f"{p} is inside the repository {repo_root}; keep sources and outputs outside the repo")


def tracked_files(repo_root: Path = REPO_ROOT) -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                             cwd=repo_root, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [l for l in out.splitlines() if l.strip()]


def forbidden_tracked(repo_root: Path = REPO_ROOT) -> list[str]:
    """Files that git would commit and that look like source documents."""
    return [f for f in tracked_files(repo_root) if Path(f).suffix.lower() in FORBIDDEN_SUFFIXES]
