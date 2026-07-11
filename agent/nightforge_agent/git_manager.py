"""
Git operations for a project working copy (subprocess-based).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

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
