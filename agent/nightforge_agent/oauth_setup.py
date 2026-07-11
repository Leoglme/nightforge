"""
Configure Claude Code to fetch OAuth tokens through NightForge's apiKeyHelper.
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


def is_frozen_bundle() -> bool:
    return getattr(sys, "frozen", False)


def oauth_helper_script_path() -> Path:
    return Path(__file__).resolve().parent.parent / "scripts" / "nightforge_oauth_helper.py"


def api_key_helper_command() -> str:
    if is_frozen_bundle():
        return f'"{sys.executable}" {OAUTH_TOKEN_FLAG}'
    script = oauth_helper_script_path()
    return f'"{sys.executable}" "{script}"'


def _helper_command_is_broken(current: str) -> bool:
    lowered = current.lower()
    return (
        "_mei" in lowered
        or "nightforge_oauth_helper.py" in lowered
        and is_frozen_bundle()
        and OAUTH_TOKEN_FLAG not in lowered
    )


def ensure_api_key_helper_configured() -> None:
    """
    Point Claude Code's ``apiKeyHelper`` at NightForge when not already customized.
    """
    settings_path = claude_config_dir() / "settings.json"
    settings: dict = {}
    if settings_path.is_file():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings = loaded
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read Claude settings (%s): %s", settings_path, exc)

    command = api_key_helper_command()
    current = settings.get("apiKeyHelper")
    if isinstance(current, str) and current.strip():
        if current == command:
            return
        if (
            HELPER_MARKER not in current
            and OAUTH_TOKEN_FLAG not in current
            and not _helper_command_is_broken(current)
        ):
            logger.debug("Keeping existing Claude apiKeyHelper configuration")
            return
        if _helper_command_is_broken(current):
            logger.info("Repairing broken Claude apiKeyHelper configuration")

    settings["apiKeyHelper"] = command
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        logger.info("Configured Claude Code apiKeyHelper for automatic OAuth refresh")
    except OSError as exc:
        logger.warning("Could not update Claude settings (%s): %s", settings_path, exc)
