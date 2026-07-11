"""
Load and refresh Claude OAuth credentials from the local Claude Code install.

Claude Code stores tokens in ``~/.claude/.credentials.json``. The refresh endpoint
migrated to ``platform.claude.com``; we try the new host first, then the legacy
console host, with JSON and form-encoded bodies for compatibility.
"""
from __future__ import annotations

import json
import logging
import os
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


def claude_config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))


def credentials_path() -> Path:
    return claude_config_dir() / ".credentials.json"


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
        return oauth

    if sys.platform != "win32":
        return oauth

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
            return candidate
    return oauth


async def refresh_oauth_token(oauth: dict[str, Any]) -> Optional[dict[str, Any]]:
    refresh_token = oauth.get("refreshToken")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        logger.warning(
            "Claude OAuth access token expired and no refresh token is available — run `claude auth login`"
        )
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
                except OSError as exc:
                    logger.warning("Could not persist refreshed OAuth token: %s", exc)
                return updated
    return None


def oauth_unavailable_reason(oauth: Optional[dict[str, Any]]) -> Optional[str]:
    """Human-readable reason OAuth cannot be used right now."""
    if oauth is None:
        return "Aucun compte Claude connecté sur cette machine (`claude auth login`)."
    if not oauth.get("accessToken"):
        return "Jeton Claude manquant — reconnecte-toi avec `claude auth login`."
    if token_expired(oauth) and not str(oauth.get("refreshToken") or "").strip():
        return "Session Claude expirée — lance `claude auth login` sur ce PC pour relire le quota."
    return None
