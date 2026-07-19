"""
Git operations for a project working copy (subprocess-based).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


async def _run_git(cwd: str, *args: str) -> tuple[int, str]:
    """
    Run a git command in a directory and capture its output.

    Args:
        cwd: Working directory (the repo clone).
        *args: Git arguments.

    Returns:
        A tuple of (return code, combined stdout/stderr).
    """
    process = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate()
    return process.returncode or 0, stdout.decode(errors="replace")


def night_branch_name() -> str:
    """
    Build the dedicated night branch name for today.

    Returns:
        A branch name like ``night/2026-07-11``.
    """
    return f"night/{date.today().isoformat()}"


def folder_name_from_path(path: str) -> str:
    """
    Derive a project display name from a local path.

    Args:
        path: Absolute or relative filesystem path.

    Returns:
        The last path segment, or ``projet`` if empty.
    """
    cleaned = path.rstrip("/\\")
    name = Path(cleaned).name.strip()
    return name or "projet"


def parse_github_repo(remote_url: str) -> str | None:
    """
    Normalize a git remote URL to ``owner/repo``.

    Args:
        remote_url: Output of ``git remote get-url``.

    Returns:
        ``owner/repo`` or None if not a recognizable GitHub-style remote.
    """
    text = remote_url.strip()
    if not text:
        return None

    # git@github.com:owner/repo.git
    ssh_match = re.match(r"^git@[^:]+:(.+)$", text)
    if ssh_match:
        return _strip_git_suffix(ssh_match.group(1))

    # ssh://git@github.com/owner/repo.git
    if text.startswith("ssh://"):
        parsed = urlparse(text)
        return _strip_git_suffix(parsed.path.lstrip("/")) or None

    # https://github.com/owner/repo.git
    if "://" in text:
        parsed = urlparse(text)
        return _strip_git_suffix(parsed.path.lstrip("/")) or None

    # already owner/repo
    if "/" in text and " " not in text:
        return _strip_git_suffix(text)

    return None


def _strip_git_suffix(path: str) -> str:
    """Remove a trailing ``.git`` and trailing slashes."""
    value = path.strip().rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    return value


async def ensure_clean(cwd: str) -> bool:
    """
    Check the working tree is clean.

    Args:
        cwd: The repo clone.

    Returns:
        True if there are no uncommitted changes.
    """
    code, out = await _run_git(cwd, "status", "--porcelain")
    return code == 0 and out.strip() == ""


async def create_night_branch(cwd: str, base_branch: str) -> str:
    """
    Create (or switch to) the dedicated night branch from the base branch.

    Args:
        cwd: The repo clone.
        base_branch: The branch to start from.

    Returns:
        The night branch name.
    """
    branch = night_branch_name()
    await _run_git(cwd, "fetch", "origin", base_branch)
    await _run_git(cwd, "checkout", base_branch)
    await _run_git(cwd, "checkout", "-B", branch)
    return branch


async def ensure_on_branch(cwd: str, branch: str) -> str:
    """
    Check out ``branch`` (typically ``main``) for direct pushes.

    Args:
        cwd: The repo clone.
        branch: Target branch name.

    Returns:
        The branch name.
    """
    await _run_git(cwd, "fetch", "origin", branch)
    await _run_git(cwd, "checkout", branch)
    # Soft sync with remote tip when possible (ignore failures on fresh clones).
    await _run_git(cwd, "pull", "--ff-only", "origin", branch)
    return branch


async def inspect_repo(cwd: str) -> dict[str, Any]:
    """
    Read folder name, GitHub remote and current/default branch from a local path.

    Args:
        cwd: Absolute path that should contain a git clone.

    Returns:
        Dict with ``exists``, ``is_git``, optional ``name`` / ``github_repo`` /
        ``base_branch`` / ``error``.
    """
    path = cwd.strip()
    if not path:
        return {"exists": False, "is_git": False, "error": "empty path"}

    if not os.path.isdir(path):
        return {"exists": False, "is_git": False, "name": folder_name_from_path(path), "error": "path not found"}

    name = folder_name_from_path(path)
    code, _ = await _run_git(path, "rev-parse", "--is-inside-work-tree")
    if code != 0:
        return {"exists": True, "is_git": False, "name": name, "error": "not a git repository"}

    github_repo = None
    remote_code, remote_out = await _run_git(path, "remote", "get-url", "origin")
    if remote_code == 0:
        github_repo = parse_github_repo(remote_out.splitlines()[0] if remote_out else "")

    base_branch = None
    head_code, head_out = await _run_git(path, "symbolic-ref", "refs/remotes/origin/HEAD")
    if head_code == 0 and head_out.strip():
        # refs/remotes/origin/main → main
        ref = head_out.strip().split("/")[-1]
        if ref:
            base_branch = ref
    if not base_branch:
        cur_code, cur_out = await _run_git(path, "rev-parse", "--abbrev-ref", "HEAD")
        if cur_code == 0 and cur_out.strip() and cur_out.strip() != "HEAD":
            base_branch = cur_out.strip()

    return {
        "exists": True,
        "is_git": True,
        "name": name,
        "github_repo": github_repo,
        "base_branch": base_branch or "main",
        "error": None,
    }


async def commit_all(cwd: str, message: str) -> None:
    """
    Stage and commit all changes.

    Args:
        cwd: The repo clone.
        message: Commit message (conventional commit).
    """
    await _run_git(cwd, "add", "-A")
    await _run_git(cwd, "commit", "-m", message)


async def push(cwd: str, branch: str) -> None:
    """
    Push a branch to origin.

    Args:
        cwd: The repo clone.
        branch: The branch to push.
    """
    await _run_git(cwd, "push", "-u", "origin", branch)
