"""
Agent configuration loaded from environment variables and a shared provisioning file.

The provisioning file (``~/.nightforge/agent.json``) lets the desktop app configure the
machine in one click: it registers the machine against the control-plane and drops the
token here, which the agent (running as a Tauri sidecar) picks up automatically — no manual
``.env`` editing required.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

#: Shared file written by the desktop app ("Ajouter cette machine") and read by the agent.
PROVISION_PATH = Path.home() / ".nightforge" / "agent.json"


@dataclass
class AgentConfig:
    """
    Runtime configuration for the agent.

    Attributes:
        api_base: Control-plane base URL (http/https).
        agent_token: Machine token used to authenticate the WebSocket.
        claude_bin: Path or name of the Claude Code CLI.
        tick_seconds: Heartbeat / quota poll interval.
        quota_retry_seconds: Fallback wait before retrying after a quota hit with no reset hint.
        error_budget: Consecutive item failures tolerated before aborting a run.
    """

    api_base: str
    agent_token: str
    claude_bin: str
    tick_seconds: int
    quota_retry_seconds: int
    error_budget: int

    @property
    def ws_url(self) -> str:
        """
        Build the agent WebSocket URL from the API base.

        Returns:
            The ws(s):// URL including the token query.
        """
        base = self.api_base.rstrip("/")
        ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
        return f"{ws_base}/api/v1/ws/agent?token={self.agent_token}"


def _read_provision_file() -> dict:
    """
    Read the shared provisioning file written by the desktop app.

    Returns:
        The parsed JSON payload, or an empty dict if absent or unreadable.
    """
    try:
        with PROVISION_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("Could not read provisioning file %s: %s", PROVISION_PATH, exc)
        return {}


def try_load_config() -> Optional[AgentConfig]:
    """
    Build the agent configuration, preferring env vars and falling back to the shared file.

    Resolution order for each value: environment variable → ``.env`` → provisioning file →
    default. The agent token has no default: if it cannot be found, ``None`` is returned so
    the caller can wait for provisioning.

    Returns:
        The parsed configuration, or ``None`` if no agent token is available yet.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    provisioned = _read_provision_file()

    token = (os.environ.get("NF_AGENT_TOKEN") or provisioned.get("agent_token") or "").strip()
    if not token:
        return None

    api_base = (
        os.environ.get("NF_API_BASE")
        or provisioned.get("api_base")
        or "http://localhost:8010"
    )

    return AgentConfig(
        api_base=api_base,
        agent_token=token,
        claude_bin=os.environ.get("NF_CLAUDE_BIN", "claude"),
        tick_seconds=int(os.environ.get("NF_TICK_SECONDS", "30")),
        quota_retry_seconds=int(os.environ.get("NF_QUOTA_RETRY_SECONDS", "900")),
        error_budget=int(os.environ.get("NF_ERROR_BUDGET", "3")),
    )


def load_config(*, wait: bool = False, poll_seconds: int = 5) -> AgentConfig:
    """
    Load the agent configuration, optionally waiting for provisioning.

    When ``wait`` is True (the sidecar case) and no token is available yet, the agent polls
    the provisioning file until the desktop app registers this machine, instead of exiting.
    This is what lets "opening the app" be enough to start everything.

    Args:
        wait: Poll for provisioning instead of raising when no token is found.
        poll_seconds: Interval between provisioning checks when waiting.

    Returns:
        The parsed agent configuration.

    Raises:
        SystemExit: If ``wait`` is False and the required agent token is missing.
    """
    config = try_load_config()
    if config is not None:
        return config

    if not wait:
        raise SystemExit(
            "No agent token found. Register this machine from the dashboard "
            f"(NF_AGENT_TOKEN or {PROVISION_PATH})."
        )

    logger.info(
        'Waiting for provisioning — open NightForge and click "Ajouter cette machine" '
        "(watching %s)",
        PROVISION_PATH,
    )
    while config is None:
        time.sleep(poll_seconds)
        config = try_load_config()
    logger.info("Provisioning detected; connecting to %s", config.api_base)
    return config
