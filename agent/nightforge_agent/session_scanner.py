"""
Claude Code session scanner — lists resumable conversations stored under ~/.claude/projects.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


@dataclass
class ClaudeSession:
    """
    A resumable Claude Code session on disk.

    Attributes:
        session_id: UUID used with ``claude --resume``.
        title: Custom display name from the session transcript, if any.
        cwd: Working directory the session was started in.
        updated_at: Last modification time of the transcript file.
    """

    session_id: str
    title: Optional[str]
    cwd: Optional[str]
    updated_at: datetime


def _claude_config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))


def encode_project_path(cwd: str) -> str:
    """
    Encode a local path the same way Claude Code names its project folder.

    Args:
        cwd: Absolute project working directory.

    Returns:
        Folder name under ``~/.claude/projects/``.
    """
    resolved = str(Path(cwd).resolve())
    return resolved.replace("\\", "-").replace("/", "-").replace(":", "-")


def _parse_title(jsonl_path: Path) -> Optional[str]:
    try:
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(40):
                line = handle.readline()
                if not line:
                    break
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") == "custom-title":
                    title = entry.get("customTitle")
                    if isinstance(title, str) and title.strip():
                        return title.strip()
    except OSError:
        return None
    return None


def _parse_cwd(jsonl_path: Path) -> Optional[str]:
    try:
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(80):
                line = handle.readline()
                if not line:
                    break
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cwd = entry.get("cwd")
                if isinstance(cwd, str) and cwd.strip():
                    return cwd.strip()
    except OSError:
        return None
    return None


def list_sessions(cwd: str, limit: int = 30) -> List[ClaudeSession]:
    """
    List recent Claude Code sessions for a project directory.

    Args:
        cwd: Local clone path of the project.
        limit: Maximum sessions to return.

    Returns:
        Sessions sorted by most recently updated first.
    """
    project_dir = _claude_config_dir() / "projects" / encode_project_path(cwd)
    if not project_dir.is_dir():
        return []

    sessions: List[ClaudeSession] = []
    for jsonl_path in project_dir.glob("*.jsonl"):
        if not jsonl_path.is_file():
            continue
        try:
            mtime = datetime.fromtimestamp(jsonl_path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        sessions.append(
            ClaudeSession(
                session_id=jsonl_path.stem,
                title=_parse_title(jsonl_path),
                cwd=_parse_cwd(jsonl_path),
                updated_at=mtime,
            )
        )

    sessions.sort(key=lambda item: item.updated_at, reverse=True)
    return sessions[:limit]


def find_latest_session_id(cwd: str, not_before: float) -> Optional[str]:
    """
    Return the session id of the newest transcript touched after a timestamp.

    Args:
        cwd: Project working directory.
        not_before: Unix epoch seconds — ignore older files.

    Returns:
        Session UUID or None.
    """
    project_dir = _claude_config_dir() / "projects" / encode_project_path(cwd)
    if not project_dir.is_dir():
        return None

    best_id: Optional[str] = None
    best_mtime = not_before - 1.0
    for jsonl_path in project_dir.glob("*.jsonl"):
        try:
            mtime = jsonl_path.stat().st_mtime
        except OSError:
            continue
        if mtime >= not_before - 2.0 and mtime > best_mtime:
            best_mtime = mtime
            best_id = jsonl_path.stem
    return best_id
