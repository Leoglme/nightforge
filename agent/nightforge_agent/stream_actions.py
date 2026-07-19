"""
Parse Claude / Cursor stream-json tool events into NightForge chat actions.

Emitted events use the prefix ``__NF_ACTION__:`` followed by a compact JSON
payload so the web UI can render Claude-Code-style file review sheets.
"""
from __future__ import annotations

import difflib
import json
from typing import Any, Optional

#: Marker prefix for structured tool actions in run event messages.
NF_ACTION_PREFIX = "__NF_ACTION__:"

#: Soft cap so a single edit does not blow up WebSocket / DB rows.
_MAX_DIFF_CHARS = 80_000

_EDIT_TOOLS = frozenset({"Edit", "edit", "StrReplace", "str_replace"})
_WRITE_TOOLS = frozenset({"Write", "write", "Create", "create"})
_READ_TOOLS = frozenset({"Read", "read", "ReadFile", "read_file"})
_BASH_TOOLS = frozenset({"Bash", "bash", "Shell", "shell", "Terminal", "terminal"})


def encode_action(payload: dict[str, Any]) -> str:
    """
    Serialize a tool action for emission as a run event message.

    Args:
        payload: Action dict (kind, path, additions, deletions, diff, detail).

    Returns:
        A single-line ``__NF_ACTION__:…`` string.
    """
    return f"{NF_ACTION_PREFIX}{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"


def looks_like_unified_diff(text: str) -> bool:
    """Return True when ``text`` looks like a git / unified diff."""
    if not text or len(text) < 12:
        return False
    head = text.lstrip()[:800]
    return (
        "diff --git " in head
        or head.startswith("--- ")
        or "\n--- " in head
        or head.startswith("+++ ")
        or "@@ " in head
    )


def is_git_diff_command(command: str) -> bool:
    """True when a shell command is likely producing a git diff for review."""
    lowered = command.lower()
    return "git" in lowered and "diff" in lowered


def _count_diff_stats(diff_body: str) -> tuple[int, int]:
    """Count added / removed lines in a unified diff body."""
    additions = 0
    deletions = 0
    for line in diff_body.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return additions, deletions


def actions_from_unified_diff(diff_text: str) -> list[dict[str, Any]]:
    """
    Split a multi-file unified / git diff into one NF edit action per file.

    Args:
        diff_text: Raw ``git diff`` / unified diff output.

    Returns:
        List of edit action dicts (may be empty).
    """
    if not looks_like_unified_diff(diff_text):
        return []

    lines = diff_text.replace("\r\n", "\n").split("\n")
    chunks: list[tuple[str, list[str]]] = []
    current_path = ""
    current: list[str] = []

    def flush() -> None:
        nonlocal current_path, current
        body = current
        path = current_path
        current_path = ""
        current = []
        if not body:
            return
        if not path:
            for row in body:
                if row.startswith("+++ b/"):
                    path = row[6:].strip()
                    break
                if row.startswith("+++ ") and not row.startswith("+++ /dev/null"):
                    path = row[4:].strip()
                    if path.startswith("b/"):
                        path = path[2:]
                    break
                if row.startswith("--- a/"):
                    path = row[6:].strip()
                elif row.startswith("--- ") and "/dev/null" not in row:
                    path = row[4:].strip()
                    if path.startswith("a/"):
                        path = path[2:]
        if path == "/dev/null":
            path = ""
        if path or any(r.startswith(("+", "-", "@")) for r in body):
            chunks.append((path or "file", body))

    for line in lines:
        if line.startswith("diff --git "):
            flush()
            parts = line.split()
            path = ""
            if len(parts) >= 4:
                path = parts[3]
                if path.startswith("b/"):
                    path = path[2:]
            current_path = path
            current = [line]
            continue
        if not current and line.startswith(("--- ", "+++ ")):
            current = [line]
            continue
        if current:
            current.append(line)

    flush()

    actions: list[dict[str, Any]] = []
    for path, body_lines in chunks:
        body = "\n".join(body_lines)
        if len(body) > _MAX_DIFF_CHARS:
            body = body[:_MAX_DIFF_CHARS] + "\n… (diff tronqué)"
        additions, deletions = _count_diff_stats(body)
        if not path and not additions and not deletions:
            continue
        actions.append(
            {
                "kind": "edit",
                "path": path,
                "additions": additions,
                "deletions": deletions,
                "diff": body,
            }
        )
    return actions


def _tool_result_text(block: dict[str, Any]) -> str:
    """Normalize a tool_result content field to a plain string."""
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(parts)
    return str(content or "")


def build_unified_diff(old: str, new: str, *, path: str = "") -> tuple[str, int, int]:
    """
    Build a compact unified-style diff and count added / removed lines.

    Args:
        old: Previous content (empty for creates).
        new: New content.
        path: Optional path label in the header.

    Returns:
        ``(diff_text, additions, deletions)``.
    """
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    label = path or "file"
    hunks = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{label}",
            tofile=f"b/{label}",
            lineterm="",
            n=3,
        )
    )
    additions = sum(1 for line in hunks if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in hunks if line.startswith("-") and not line.startswith("---"))
    body = "\n".join(hunks)
    if len(body) > _MAX_DIFF_CHARS:
        body = body[:_MAX_DIFF_CHARS] + "\n… (diff tronqué)"
    return body, additions, deletions


def action_from_claude_tool(name: str, tool_input: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Map a Claude Code ``tool_use`` block to an NF action payload.

    Args:
        name: Tool name (Edit, Write, Read, Bash, …).
        tool_input: Tool input object.

    Returns:
        Action dict, or None when the tool is not review-relevant.
    """
    if not isinstance(tool_input, dict):
        tool_input = {}

    if name in _EDIT_TOOLS:
        path = str(tool_input.get("file_path") or tool_input.get("path") or "")
        old = str(tool_input.get("old_string") or tool_input.get("old_str") or "")
        new = str(tool_input.get("new_string") or tool_input.get("new_str") or "")
        diff, additions, deletions = build_unified_diff(old, new, path=path)
        return {
            "kind": "edit",
            "path": path,
            "additions": additions,
            "deletions": deletions,
            "diff": diff,
        }

    if name in _WRITE_TOOLS:
        path = str(tool_input.get("file_path") or tool_input.get("path") or "")
        content = str(tool_input.get("content") or tool_input.get("file_text") or "")
        diff, additions, deletions = build_unified_diff("", content, path=path)
        return {
            "kind": "write",
            "path": path,
            "additions": additions or max(content.count("\n") + (1 if content else 0), 0),
            "deletions": deletions,
            "diff": diff,
        }

    if name in _READ_TOOLS:
        path = str(tool_input.get("file_path") or tool_input.get("path") or "")
        return {"kind": "read", "path": path, "additions": 0, "deletions": 0}

    if name in _BASH_TOOLS:
        command = str(tool_input.get("command") or tool_input.get("cmd") or "")
        # git diff → wait for tool_result so we can emit per-file review actions.
        if is_git_diff_command(command):
            return None
        return {
            "kind": "bash",
            "detail": command[:2000],
            "additions": 0,
            "deletions": 0,
        }

    return None


def action_from_cursor_tool_call(tool_call: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Map a Cursor ``tool_call`` object (started or completed) to an NF action.

    Prefers completed payloads (diff stats) when available.

    Args:
        tool_call: The ``tool_call`` field from a Cursor stream-json event.

    Returns:
        Action dict, or None when irrelevant / incomplete.
    """
    if not isinstance(tool_call, dict):
        return None

    if "editToolCall" in tool_call:
        block = tool_call["editToolCall"] or {}
        args = block.get("args") or {}
        result = (block.get("result") or {}).get("success") or {}
        path = str(result.get("path") or args.get("path") or "")
        diff = str(result.get("diffString") or "")
        additions = int(result.get("linesAdded") or 0)
        deletions = int(result.get("linesRemoved") or 0)
        if not diff and args.get("fileText") is not None:
            content = str(args.get("fileText") or "")
            diff, additions, deletions = build_unified_diff("", content, path=path)
        elif not diff and (args.get("old_string") or args.get("new_string")):
            old = str(args.get("old_string") or "")
            new = str(args.get("new_string") or "")
            diff, additions, deletions = build_unified_diff(old, new, path=path)
        if len(diff) > _MAX_DIFF_CHARS:
            diff = diff[:_MAX_DIFF_CHARS] + "\n… (diff tronqué)"
        # Skip incomplete "started" events with no path and no stats.
        if not path and not diff and not additions and not deletions:
            return None
        return {
            "kind": "edit",
            "path": path,
            "additions": additions,
            "deletions": deletions,
            "diff": diff,
        }

    if "writeToolCall" in tool_call:
        block = tool_call["writeToolCall"] or {}
        args = block.get("args") or {}
        result = (block.get("result") or {}).get("success") or {}
        path = str(result.get("path") or args.get("path") or "")
        content = str(args.get("fileText") or "")
        lines_created = result.get("linesCreated")
        if content:
            diff, additions, deletions = build_unified_diff("", content, path=path)
        else:
            additions = int(lines_created or 0)
            deletions = 0
            diff = ""
        if not path and not additions:
            return None
        return {
            "kind": "write",
            "path": path,
            "additions": additions,
            "deletions": deletions,
            "diff": diff,
        }

    if "readToolCall" in tool_call:
        block = tool_call["readToolCall"] or {}
        args = block.get("args") or {}
        path = str(args.get("path") or "")
        if not path:
            return None
        return {"kind": "read", "path": path, "additions": 0, "deletions": 0}

    if "shellToolCall" in tool_call:
        block = tool_call["shellToolCall"] or {}
        args = block.get("args") or {}
        command = str(args.get("command") or args.get("cmd") or "")
        result = block.get("result") or {}
        success = result.get("success") if isinstance(result, dict) else None
        stdout = ""
        if isinstance(success, dict):
            stdout = str(success.get("stdout") or success.get("output") or success.get("content") or "")
        elif isinstance(result, dict):
            stdout = str(result.get("stdout") or result.get("output") or "")
        if stdout and looks_like_unified_diff(stdout):
            return {
                "kind": "edit",
                "path": "",
                "additions": 0,
                "deletions": 0,
                "diff": stdout[:_MAX_DIFF_CHARS],
                "_expand_diff": True,
            }
        if is_git_diff_command(command) and not stdout:
            return None
        if not command:
            return None
        return {
            "kind": "bash",
            "detail": command[:2000],
            "additions": 0,
            "deletions": 0,
        }

    # Generic function-style fallback
    fn = tool_call.get("function")
    if isinstance(fn, dict):
        name = str(fn.get("name") or "")
        raw_args = fn.get("arguments")
        parsed: dict[str, Any] = {}
        if isinstance(raw_args, dict):
            parsed = raw_args
        elif isinstance(raw_args, str):
            try:
                loaded = json.loads(raw_args)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                parsed = {}
        return action_from_claude_tool(name, parsed)

    return None


def expand_action_if_needed(action: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Expand a placeholder action that embeds a full multi-file diff.

    Args:
        action: Possibly marked with ``_expand_diff``.

    Returns:
        One or more concrete actions.
    """
    if action.get("_expand_diff") and action.get("diff"):
        expanded = actions_from_unified_diff(str(action["diff"]))
        return expanded or [{k: v for k, v in action.items() if k != "_expand_diff"}]
    return [{k: v for k, v in action.items() if k != "_expand_diff"}]


def extract_claude_assistant_parts(event: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Extract plain text chunks and tool actions from a Claude stream-json event.

    Also turns ``tool_result`` payloads that contain a git/unified diff into
    per-file edit actions (code-review UI).

    Args:
        event: One NDJSON object from Claude ``stream-json``.

    Returns:
        ``(text_chunks, actions)``.
    """
    texts: list[str] = []
    actions: list[dict[str, Any]] = []
    event_type = event.get("type")

    if event_type == "assistant":
        message = event.get("message") or {}
        content = message.get("content") or []
        if isinstance(content, str):
            if content.strip():
                texts.append(content)
            return texts, actions
        if not isinstance(content, list):
            return texts, actions
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text = str(block.get("text") or "")
                if text.strip():
                    texts.append(text)
            elif btype == "thinking":
                thinking = str(block.get("thinking") or block.get("text") or "")
                if thinking.strip():
                    actions.append(
                        {
                            "kind": "thinking",
                            "detail": thinking[:4000],
                            "additions": 0,
                            "deletions": 0,
                        }
                    )
            elif btype == "tool_use":
                name = str(block.get("name") or "")
                tool_input = block.get("input") or {}
                if isinstance(tool_input, str):
                    try:
                        tool_input = json.loads(tool_input)
                    except json.JSONDecodeError:
                        tool_input = {}
                action = action_from_claude_tool(name, tool_input if isinstance(tool_input, dict) else {})
                if action:
                    actions.append(action)

    elif event_type == "user":
        message = event.get("message") or {}
        content = message.get("content") or []
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_result":
                    continue
                result_text = _tool_result_text(block)
                if looks_like_unified_diff(result_text):
                    actions.extend(actions_from_unified_diff(result_text))

    elif event_type == "content_block_delta":
        # Older / alternate stream shapes
        delta = event.get("delta") or {}
        if delta.get("type") == "text_delta":
            text = str(delta.get("text") or "")
            if text:
                texts.append(text)

    return texts, actions


def session_id_from_event(event: dict[str, Any]) -> Optional[str]:
    """Pull ``session_id`` from a Claude / Cursor stream event when present."""
    sid = event.get("session_id") or event.get("sessionId")
    if isinstance(sid, str) and sid.strip():
        return sid.strip()
    return None


def try_parse_json_line(line: str) -> Optional[dict[str, Any]]:
    """
    Parse one NDJSON line into a dict, or return None.

    Args:
        line: Raw stdout line.

    Returns:
        Parsed object, or None if not JSON.
    """
    stripped = line.strip()
    if not stripped.startswith("{"):
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
