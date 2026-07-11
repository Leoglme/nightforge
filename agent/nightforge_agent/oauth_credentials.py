"""
Load, refresh and auto-repair Claude OAuth credentials from the local Claude Code install.

NightForge keeps Claude sessions alive without manual terminal steps:
- proactive refresh before expiry when a refresh token exists
- backup of refresh tokens under ``~/.nightforge/oauth_backup.json``
- automatic ``claude auth login`` (opens the browser) when repair is needed
- optional ``apiKeyHelper`` wiring so Claude Code subprocesses reuse the same flow
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
OAUTH_REFRESH_URLS = (
    "https://platform.claude.com/v1/oauth/token",
    "https://console.anthropic.com/v1/oauth/token",
)
CLAUDE_USER_AGENT = "claude-code/2.1.172"

REFRESH_EARLY_MS = 30 * 60 * 1000
REPAIR_WAIT_SECONDS = 300.0
REPAIR_POLL_SECONDS = 2.0
REPAIR_COOLDOWN_SECONDS = 120.0

_repair_lock = asyncio.Lock()
_last_repair_attempt = 0.0
_login_process: Optional[subprocess.Popen[Any]] = None


def claude_config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))


def credentials_path() -> Path:
    return claude_config_dir() / ".credentials.json"


def nightforge_dir() -> Path:
    path = Path.home() / ".nightforge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def oauth_backup_path() -> Path:
    return nightforge_dir() / "oauth_backup.json"


def claude_bin() -> str:
    return os.environ.get("NF_CLAUDE_BIN", "claude")


def load_oauth_block() -> Optional[dict[str, Any]]:
    """Read the ``claudeAiOauth`` block from the credentials file."""
    path = credentials_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Could not read Claude credentials: %s", exc)
        return None
    oauth = data.get("claudeAiOauth")
    return oauth if isinstance(oauth, dict) else None


def token_expired(oauth: dict[str, Any], buffer_seconds: int = 60) -> bool:
    expires_at = oauth.get("expiresAt")
    if not isinstance(expires_at, (int, float)):
        return True
    return int(expires_at) <= int(time.time() * 1000) + buffer_seconds * 1000


def token_expires_soon(oauth: dict[str, Any], buffer_ms: int = REFRESH_EARLY_MS) -> bool:
    expires_at = oauth.get("expiresAt")
    if not isinstance(expires_at, (int, float)):
        return True
    return int(expires_at) <= int(time.time() * 1000) + buffer_ms


def credentials_usable(oauth: Optional[dict[str, Any]]) -> bool:
    return bool(oauth and oauth.get("accessToken") and not token_expired(oauth))


def write_oauth_block(oauth: dict[str, Any]) -> None:
    path = credentials_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    payload["claudeAiOauth"] = oauth
    tmp = path.with_suffix(".credentials.json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def backup_oauth(oauth: dict[str, Any]) -> None:
    refresh = str(oauth.get("refreshToken") or "").strip()
    if not refresh:
        return
    payload = {
        "refreshToken": refresh,
        "saved_at": int(time.time() * 1000),
    }
    try:
        oauth_backup_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.debug("Could not persist OAuth backup: %s", exc)


def merge_backup_refresh(oauth: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if oauth is None:
        oauth = {}
    if str(oauth.get("refreshToken") or "").strip():
        return oauth
    backup_path = oauth_backup_path()
    if not backup_path.is_file():
        return oauth or None
    try:
        backup = json.loads(backup_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return oauth or None
    refresh = backup.get("refreshToken")
    if not isinstance(refresh, str) or not refresh.strip():
        return oauth or None
    merged = {**oauth, "refreshToken": refresh.strip()}
    logger.info("Restored Claude refresh token from NightForge backup")
    try:
        write_oauth_block(merged)
    except OSError as exc:
        logger.debug("Could not write merged OAuth block: %s", exc)
    return merged


def _read_windows_credential(target: str) -> Optional[str]:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None

    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    advapi32 = ctypes.windll.advapi32
    pcred = ctypes.POINTER(CREDENTIALW)()
    if not advapi32.CredReadW(target, 1, 0, ctypes.byref(pcred)):
        return None
    try:
        blob = ctypes.string_at(pcred.contents.CredentialBlob, pcred.contents.CredentialBlobSize)
        return blob.decode("utf-8", errors="replace")
    finally:
        advapi32.CredFree(pcred)


def load_oauth_block_with_fallback() -> Optional[dict[str, Any]]:
    """
    Load OAuth credentials from the JSON file, then Windows Credential Manager.
    """
    oauth = load_oauth_block()
    if oauth and oauth.get("accessToken"):
        return merge_backup_refresh(oauth)

    if sys.platform != "win32":
        return merge_backup_refresh(oauth)

    for target in ("Claude Code-credentials", "Claude Code"):
        raw = _read_windows_credential(target)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidate = data.get("claudeAiOauth")
        if isinstance(candidate, dict) and candidate.get("accessToken"):
            logger.info("Loaded Claude OAuth from Windows Credential Manager (%s)", target)
            return merge_backup_refresh(candidate)
    return merge_backup_refresh(oauth)


async def refresh_oauth_token(oauth: dict[str, Any]) -> Optional[dict[str, Any]]:
    refresh_token = oauth.get("refreshToken")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        logger.warning("Claude OAuth access token expired and no refresh token is available")
        return None

    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": OAUTH_CLIENT_ID,
    }
    headers = {"User-Agent": CLAUDE_USER_AGENT}
    attempts = (
        ("json", {"json": body}),
        ("form", {"data": body}),
    )

    async with httpx.AsyncClient(timeout=20.0) as client:
        for url in OAUTH_REFRESH_URLS:
            for label, kwargs in attempts:
                try:
                    response = await client.post(url, headers=headers, **kwargs)
                except httpx.HTTPError as exc:
                    logger.debug("OAuth refresh %s (%s) failed: %s", url, label, exc)
                    continue
                if response.status_code != 200:
                    logger.debug(
                        "OAuth refresh %s (%s) rejected (%s): %s",
                        url,
                        label,
                        response.status_code,
                        response.text[:200],
                    )
                    continue
                data = response.json()
                updated = {
                    **oauth,
                    "accessToken": data["access_token"],
                    "refreshToken": data.get("refresh_token", refresh_token),
                    "expiresAt": int(time.time() * 1000) + int(data.get("expires_in", 3600)) * 1000,
                }
                try:
                    write_oauth_block(updated)
                    backup_oauth(updated)
                except OSError as exc:
                    logger.warning("Could not persist refreshed OAuth token: %s", exc)
                logger.info("Claude OAuth access token refreshed automatically")
                return updated
    return None


def _spawn_claude_login() -> None:
    global _login_process
    if _login_process is not None and _login_process.poll() is None:
        return

    binary = shutil.which(claude_bin()) or claude_bin()
    command = [binary, "auth", "login", "--claudeai"]
    logger.info("Opening browser to restore Claude session (%s)", " ".join(command))

    if sys.platform == "win32":
        _login_process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        )
    else:
        _login_process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


async def wait_for_fresh_credentials(
    timeout: float = REPAIR_WAIT_SECONDS,
    poll_seconds: float = REPAIR_POLL_SECONDS,
) -> Optional[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        oauth = load_oauth_block_with_fallback()
        if credentials_usable(oauth):
            return oauth
        if oauth and str(oauth.get("refreshToken") or "").strip():
            refreshed = await refresh_oauth_token(oauth)
            if credentials_usable(refreshed):
                return refreshed
        await asyncio.sleep(poll_seconds)
    return None


async def repair_oauth_session() -> bool:
    """
    Launch Claude login in the browser and wait until credentials are usable again.
    """
    global _last_repair_attempt

    async with _repair_lock:
        now = time.monotonic()
        if now - _last_repair_attempt < REPAIR_COOLDOWN_SECONDS:
            oauth = load_oauth_block_with_fallback()
            if credentials_usable(oauth):
                return True
            remaining = REPAIR_COOLDOWN_SECONDS - (now - _last_repair_attempt)
            logger.debug("Claude OAuth repair cooldown (%.0fs left)", remaining)

        _last_repair_attempt = now
        _spawn_claude_login()
        restored = await wait_for_fresh_credentials()
        if restored is not None:
            backup_oauth(restored)
            logger.info("Claude OAuth session restored automatically")
            return True

        logger.warning(
            "Claude OAuth auto-repair did not complete in time — "
            "finish sign-in in the browser if a tab opened."
        )
        return False


async def ensure_valid_oauth(*, auto_repair: bool = True) -> Optional[dict[str, Any]]:
    """
    Return OAuth credentials with a valid access token, refreshing or repairing as needed.
    """
    oauth = load_oauth_block_with_fallback()

    if credentials_usable(oauth):
        assert oauth is not None
        if token_expires_soon(oauth) and str(oauth.get("refreshToken") or "").strip():
            refreshed = await refresh_oauth_token(oauth)
            if credentials_usable(refreshed):
                return refreshed
        return oauth

    if oauth and str(oauth.get("refreshToken") or "").strip():
        refreshed = await refresh_oauth_token(oauth)
        if credentials_usable(refreshed):
            return refreshed

    if not auto_repair:
        return None

    if await repair_oauth_session():
        return load_oauth_block_with_fallback()
    return None


def ensure_valid_oauth_sync(*, auto_repair: bool = True) -> Optional[str]:
    """Sync helper for apiKeyHelper — returns a valid access token string."""
    oauth = asyncio.run(ensure_valid_oauth(auto_repair=auto_repair))
    if not credentials_usable(oauth):
        return None
    assert oauth is not None
    token = oauth.get("accessToken")
    return token if isinstance(token, str) and token else None


def oauth_unavailable_reason(
    oauth: Optional[dict[str, Any]],
    *,
    repairing: bool = False,
) -> Optional[str]:
    """Human-readable reason OAuth cannot be used right now."""
    if repairing:
        return (
            "Reconnexion Claude en cours — NightForge ouvre le navigateur automatiquement. "
            "Aucune action dans le terminal n'est nécessaire."
        )
    if oauth is None:
        return (
            "Session Claude absente sur cette machine — reconnexion automatique en cours."
        )
    if not oauth.get("accessToken"):
        return "Jeton Claude manquant — reconnexion automatique en cours."
    if token_expired(oauth) and not str(oauth.get("refreshToken") or "").strip():
        return (
            "Session Claude expirée — NightForge tente une reconnexion automatique via le navigateur."
        )
    return None
