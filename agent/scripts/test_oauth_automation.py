"""Tests for automatic Claude OAuth refresh and repair."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_ROOT))

from nightforge_agent import oauth_credentials  # noqa: E402


async def test_refresh_when_expired() -> None:
    oauth = {
        "accessToken": "old",
        "refreshToken": "refresh-abc",
        "expiresAt": int(time.time() * 1000) - 1000,
    }
    updated = {
        "accessToken": "new",
        "refreshToken": "refresh-xyz",
        "expiresAt": int(time.time() * 1000) + 3_600_000,
    }

    with patch.object(oauth_credentials, "load_oauth_block_with_fallback", return_value=oauth):
        with patch.object(oauth_credentials, "refresh_oauth_token", AsyncMock(return_value=updated)):
            result = await oauth_credentials.ensure_valid_oauth(auto_repair=False)

    assert result is not None
    assert result["accessToken"] == "new"
    print("OK test_refresh_when_expired")


async def test_repair_spawned_when_no_refresh() -> None:
    oauth = {
        "accessToken": "old",
        "refreshToken": "",
        "expiresAt": int(time.time() * 1000) - 1000,
    }
    restored = {
        "accessToken": "fresh",
        "refreshToken": "rotated",
        "expiresAt": int(time.time() * 1000) + 3_600_000,
    }

    with patch.object(oauth_credentials, "load_oauth_block_with_fallback", return_value=oauth):
        with patch.object(oauth_credentials, "refresh_oauth_token", AsyncMock(return_value=None)):
            with patch.object(oauth_credentials, "_spawn_claude_login") as spawn:
                with patch.object(
                    oauth_credentials,
                    "wait_for_fresh_credentials",
                    AsyncMock(return_value=restored),
                ):
                    ok = await oauth_credentials.repair_oauth_session()

    assert ok is True
    spawn.assert_called_once()
    print("OK test_repair_spawned_when_no_refresh")


def test_api_key_helper_command() -> None:
    from nightforge_agent.oauth_setup import api_key_helper_command, oauth_helper_script_path

    assert oauth_helper_script_path().is_file()
    assert "nightforge_oauth_helper.py" in api_key_helper_command()
    print("OK test_api_key_helper_command")


if __name__ == "__main__":
    asyncio.run(test_refresh_when_expired())
    asyncio.run(test_repair_spawned_when_no_refresh())
    test_api_key_helper_command()
    print("ALL OAUTH TESTS PASSED")
