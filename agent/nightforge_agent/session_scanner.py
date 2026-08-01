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
        active: Whether the last turn is still in progress (Claude working).
    """

    session_id: str
    title: Optional[str]
    cwd: Optional[str]
    updated_at: datetime
    active: bool = False


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


_DONE_STOP_REASONS = {"end_turn", "stop_sequence", "max_tokens"}
_TAIL_READ_BYTES = 65536


def _read_last_json_entry(jsonl_path: Path) -> Optional[dict]:
    """
    Read the last complete JSON entry of a transcript without loading the whole file.

    Args:
        jsonl_path: The transcript path.

    Returns:
        The last parseable entry, or None.
    """
    try:
        with jsonl_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - _TAIL_READ_BYTES))
            chunk = handle.read()
    except OSError:
        return None
    for line in reversed(chunk.decode("utf-8", errors="replace").splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            return entry
    return None


def _session_in_progress(jsonl_path: Path) -> bool:
    """
    Whether a session's last turn is still running (Claude working), from its last entry.

    A finished turn ends with an assistant message whose ``stop_reason`` is ``end_turn``
    (or similar); a pending tool call, or a user prompt / tool result not yet answered,
    means Claude is still working.

    Args:
        jsonl_path: The transcript path.

    Returns:
        True while the session is actively working.
    """
    entry = _read_last_json_entry(jsonl_path)
    if entry is None:
        return False
    entry_type = entry.get("type")
    if entry_type == "assistant":
        message = entry.get("message")
        stop_reason = message.get("stop_reason") if isinstance(message, dict) else None
        return stop_reason == "tool_use"
    if entry_type == "user":
        return True
    return False


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
                active=_session_in_progress(jsonl_path),
            )
        )

    sessions.sort(key=lambda item: item.updated_at, reverse=True)
    return sessions[:limit]


def list_all_sessions(limit: int = 40) -> List[ClaudeSession]:
    """
    List recent Claude Code sessions across every project directory on the machine.

    Args:
        limit: Maximum sessions to return.

    Returns:
        Sessions from all projects, most recently updated first.
    """
    projects_dir = _claude_config_dir() / "projects"
    if not projects_dir.is_dir():
        return []

    sessions: List[ClaudeSession] = []
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
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
                    active=_session_in_progress(jsonl_path),
                )
            )

    sessions.sort(key=lambda item: item.updated_at, reverse=True)
    return sessions[:limit]


def _find_session_file(session_id: str) -> Optional[Path]:
    """
    Locate a session transcript by id across every project directory.

    Args:
        session_id: The Claude session UUID.

    Returns:
        The transcript path, or None if not found.
    """
    projects_dir = _claude_config_dir() / "projects"
    if not projects_dir.is_dir():
        return None
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        candidate = project_dir / f"{session_id}.jsonl"
        if candidate.is_file():
            return candidate
    return None


def _user_prompt_text(message: dict) -> Optional[str]:
    """
    Extract the user prompt of a transcript 'user' entry (None if it's only a tool result).

    Args:
        message: The ``message`` object of a user entry.

    Returns:
        The prompt text, or None.
    """
    content = message.get("content")
    if isinstance(content, str):
        return content if content.strip() else None
    if not isinstance(content, list):
        return None
    parts: List[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    text = "\n".join(part for part in parts if part.strip())
    return text if text.strip() else None


def build_session_transcript(session_id: str, max_turns: int = 200) -> dict:
    """
    Rebuild a Claude session's chat history from its transcript file.

    Groups the JSONL into turns (user prompt + the assistant text / tool actions that
    followed), reusing the same ``__NF_ACTION__`` encoding the live runner emits so the
    web chat renders history identically to a live run.

    Args:
        session_id: The Claude session UUID.
        max_turns: Keep only the most recent N turns.

    Returns:
        ``{"session_id", "cwd", "turns": [{"role", "content", "events": [...]}]}``.
    """
    from . import stream_actions

    result: dict = {"session_id": session_id, "cwd": None, "turns": [], "active": False}
    path = _find_session_file(session_id)
    if path is None:
        return result
    result["active"] = _session_in_progress(path)

    turns: List[dict] = []
    current: Optional[dict] = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if result["cwd"] is None and isinstance(event.get("cwd"), str):
                    result["cwd"] = event["cwd"]
                event_type = event.get("type")
                if event_type == "user":
                    message = event.get("message")
                    prompt = _user_prompt_text(message) if isinstance(message, dict) else None
                    if prompt is not None:
                        current = {"role": "user", "content": prompt, "events": []}
                        turns.append(current)
                        continue
                    _texts, actions = stream_actions.extract_claude_assistant_parts(event)
                    if current is not None:
                        for action in actions:
                            current["events"].append(
                                {"level": "info", "message": stream_actions.encode_action(action)}
                            )
                elif event_type == "assistant":
                    texts, actions = stream_actions.extract_claude_assistant_parts(event)
                    if current is None:
                        current = {"role": "user", "content": "", "events": []}
                        turns.append(current)
                    for text in texts:
                        if text.strip():
                            current["events"].append({"level": "info", "message": text})
                    for action in actions:
                        current["events"].append(
                            {"level": "info", "message": stream_actions.encode_action(action)}
                        )
    except OSError:
        return result

    result["turns"] = turns[-max_turns:] if len(turns) > max_turns else turns
    return result


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
