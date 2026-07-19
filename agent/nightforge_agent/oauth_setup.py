"""
Manage Claude Code settings related to NightForge OAuth.

NightForge must not hijack the global ``apiKeyHelper`` — that runs on every Claude Code
tab (including Cursor) even when the agent is stopped. OAuth is injected per subprocess
instead (see ``claude_runner.claude_subprocess_env``).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from .oauth_credentials import claude_config_dir

logger = logging.getLogger(__name__)

HELPER_MARKER = "nightforge_oauth_helper"
OAUTH_TOKEN_FLAG = "--oauth-token"
NIGHTFORGE_AGENT_MARKER = "nightforge-agent"


def is_frozen_bundle() -> bool:
    return getattr(sys, "frozen", False)


def oauth_helper_script_path() -> Path:
    return Path(__file__).resolve().parent.parent / "scripts" / "nightforge_oauth_helper.py"


def is_nightforge_api_key_helper(command: str) -> bool:
    """Return True when ``command`` points at NightForge's OAuth helper."""
    lowered = command.lower()
    return (
        HELPER_MARKER in lowered
        or OAUTH_TOKEN_FLAG in lowered
        or NIGHTFORGE_AGENT_MARKER in lowered
        or "nightforge_oauth_helper.py" in lowered
    )


def remove_nightforge_api_key_helper() -> bool:
    """
    Remove NightForge's ``apiKeyHelper`` entry from Claude Code settings if present.

    Returns:
        True when settings were updated.
    """
    settings_path = claude_config_dir() / "settings.json"
    if not settings_path.is_file():
        return False

    try:
        loaded = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read Claude settings (%s): %s", settings_path, exc)
        return False

    if not isinstance(loaded, dict):
        return False

    current = loaded.get("apiKeyHelper")
    if not isinstance(current, str) or not is_nightforge_api_key_helper(current):
        return False

    loaded.pop("apiKeyHelper", None)
    try:
        settings_path.write_text(json.dumps(loaded, indent=2), encoding="utf-8")
        logger.info("Removed NightForge apiKeyHelper from Claude Code settings")
    except OSError as exc:
        logger.warning("Could not update Claude settings (%s): %s", settings_path, exc)
        return False
    return True
