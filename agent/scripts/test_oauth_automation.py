"""Tests for automatic Claude OAuth refresh and repair."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_ROOT))

from nightforge_agent import oauth_credentials  # noqa: E402
from nightforge_agent.oauth_setup import (  # noqa: E402
    is_nightforge_api_key_helper,
    remove_nightforge_api_key_helper,
)


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


def test_detects_nightforge_api_key_helper() -> None:
    assert is_nightforge_api_key_helper(
        '"C:\\Users\\me\\AppData\\Local\\NightForge\\nightforge-agent.exe" --oauth-token'
    )
    assert is_nightforge_api_key_helper('"python" "nightforge_oauth_helper.py"')
    assert not is_nightforge_api_key_helper('"python" "my_custom_helper.py"')
    print("OK test_detects_nightforge_api_key_helper")


def test_removes_nightforge_api_key_helper(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "theme": "dark",
                "apiKeyHelper": '"nightforge-agent.exe" --oauth-token',
            }
        ),
        encoding="utf-8",
    )

    with patch("nightforge_agent.oauth_setup.claude_config_dir", return_value=tmp_path):
        removed = remove_nightforge_api_key_helper()

    assert removed is True
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "apiKeyHelper" not in saved
    assert saved["theme"] == "dark"
    print("OK test_removes_nightforge_api_key_helper")


if __name__ == "__main__":
    asyncio.run(test_refresh_when_expired())
    asyncio.run(test_repair_spawned_when_no_refresh())
    test_detects_nightforge_api_key_helper()
    with tempfile.TemporaryDirectory() as tmp:
        test_removes_nightforge_api_key_helper(Path(tmp))
    print("ALL OAUTH TESTS PASSED")
