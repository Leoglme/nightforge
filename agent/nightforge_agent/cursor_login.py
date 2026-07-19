"""
Cursor account capture via NoDriver (controlled Chromium).

NoDriver runs in a **dedicated thread + event loop** so the agent WebSocket /
heartbeat stay responsive. Cursor IDE ``state.vscdb`` is never touched.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse

import httpx

from . import cursor_usage_reader

logger = logging.getLogger(__name__)

LOGIN_URL = "https://cursor.com/login"
DASHBOARD_URL = "https://cursor.com/dashboard"
SESSION_COOKIE_NAMES = (
    "WorkosCursorSessionToken",
    "workos_cursor_session_token",
)
_COOKIE_URLS = (
    "https://cursor.com/",
    "https://www.cursor.com/",
    "https://cursor.com/dashboard",
    "https://www.cursor.com/dashboard",
    "https://authenticator.cursor.sh/",
    "https://authenticator.cursor.com/",
)
_POLL_INTERVAL_SEC = 1.5
_LOGIN_TIMEOUT_SEC = 15 * 60
_BROWSER_START_TIMEOUT_SEC = 45.0
_COOKIE_DEBUG_EVERY_SEC = 10.0
_CDP_TIMEOUT_SEC = 2.5
_POST_LOGIN_PATH_PREFIXES = ("/dashboard", "/settings", "/agents", "/home")

_sessions: dict[str, "LoginSession"] = {}
_sessions_lock = threading.Lock()


@dataclass
class LoginSession:
    """Thread-safe state for an in-progress NoDriver Cursor login."""

    id: str
    profile_dir: Path
    started_at: float = field(default_factory=time.monotonic)
    finished: bool = False
    error: Optional[str] = None
    captured_token: Optional[str] = None
    captured_email: Optional[str] = None
    intercepted_token: Optional[str] = None
    browser_ready: bool = False
    debug_port: Optional[int] = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    ready_event: threading.Event = field(default_factory=threading.Event)
    thread: Optional[threading.Thread] = None
    _state_lock: threading.Lock = field(default_factory=threading.Lock)


def _profiles_root() -> Path:
    root = Path.home() / ".nightforge" / "cursor-login-profiles"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalize_session_token(raw: str) -> str:
    """Decode URL-encoded cookie value to ``user_…::jwt`` form."""
    return unquote(raw.strip()).replace("%3A%3A", "::")


def _email_from_token(token: str) -> Optional[str]:
    claims = cursor_usage_reader._jwt_claims(token.split("::")[-1])  # noqa: SLF001
    for key in ("email", "preferred_username", "name"):
        value = claims.get(key)
        if isinstance(value, str) and "@" in value:
            return value.strip()
    return None


def _email_from_api_sync(token: str) -> Optional[str]:
    """Best-effort email via Cursor usage-summary (sync, for browser thread)."""
    cookie = cursor_usage_reader._cookie_from_token(token)  # noqa: SLF001
    if not cookie:
        return None
    headers = {
        "Cookie": "WorkosCursorSessionToken=" + cookie.replace("::", "%3A%3A"),
        "Accept": "application/json",
        "User-Agent": "nightforge-agent/0.1",
        "Origin": cursor_usage_reader.CURSOR_BASE,
    }
    try:
        with httpx.Client(timeout=12.0) as client:
            resp = client.get(
                f"{cursor_usage_reader.CURSOR_BASE}/api/usage-summary",
                headers=headers,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not isinstance(data, dict):
                return None
            for key in ("email", "userEmail", "user_email"):
                value = data.get(key)
                if isinstance(value, str) and "@" in value:
                    return value.strip()
            user = data.get("user")
            if isinstance(user, dict):
                for key in ("email", "emailAddress"):
                    value = user.get(key)
                    if isinstance(value, str) and "@" in value:
                        return value.strip()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Email lookup via usage-summary failed: %s", exc)
    return None


def _cookie_name_value(cookie: Any) -> tuple[Optional[str], Optional[str]]:
    """Extract name/value from a CDP Cookie, dict, or similar object."""
    name = getattr(cookie, "name", None)
    value = getattr(cookie, "value", None)
    if name is None and isinstance(cookie, dict):
        name = cookie.get("name")
        value = cookie.get("value")
    if name is None and isinstance(cookie, (list, tuple)) and len(cookie) >= 2:
        name, value = cookie[0], cookie[1]
    return (
        str(name) if name is not None else None,
        str(value) if value is not None else None,
    )


def _is_session_cookie_name(name: str) -> bool:
    normalized = name.strip().lower().replace("-", "").replace("_", "")
    if name.strip().lower() in {n.lower() for n in SESSION_COOKIE_NAMES}:
        return True
    # Tolerate slight renames (WorkOSCursorSessionToken, etc.).
    return "workoscursor" in normalized and "session" in normalized and "token" in normalized


def _token_from_cookie_value(raw: str) -> Optional[str]:
    """
    Normalize a cookie value into a usable session token.

    Accepts ``user_…::jwt``, URL-encoded ``%3A%3A``, or a bare JWT.
    """
    token = _normalize_session_token(raw)
    if not token or len(token) < 20:
        return None
    if "::" in token:
        return token
    # Bare JWT (header.payload.sig) — still usable by the usage reader.
    if token.count(".") >= 2:
        return token
    # Some builds keep opaque long tokens — accept long alphanumeric blobs.
    if len(token) >= 40:
        return token
    return None


async def _cdp_send(connection: Any, command: Any, *, timeout: float = _CDP_TIMEOUT_SEC) -> Any:
    """CDP send with a hard timeout — a dead tab must never stall the login loop."""
    return await asyncio.wait_for(connection.send(command), timeout=timeout)


def _hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().rstrip(".")
    except Exception:  # noqa: BLE001
        return ""


def _is_cursor_app_host(host: str) -> bool:
    return host in {"cursor.com", "www.cursor.com"}


def _is_cursor_post_login_url(url: str) -> bool:
    """
    True only for real app pages like cursor.com/dashboard.

    Must NOT match authenticator.cursor.sh/?…returnTo=…%2Fdashboard — that
    false positive used to abort login mid-password and navigate away.
    """
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return False
    if not _is_cursor_app_host((parsed.hostname or "").lower().rstrip(".")):
        return False
    path = (parsed.path or "/").lower()
    return any(path == prefix or path.startswith(prefix + "/") for prefix in _POST_LOGIN_PATH_PREFIXES)


def _browser_debug_port(browser: Any) -> Optional[int]:
    config = getattr(browser, "config", None)
    if config is not None:
        port = getattr(config, "port", None)
        if isinstance(port, int) and port > 0:
            return port
        for attr in ("remote_debugging_port", "debug_port"):
            port = getattr(config, attr, None)
            if isinstance(port, int) and port > 0:
                return port
    return None


def _cdp_recv_result(ws: Any, expected_id: int, *, timeout: float = 3.0) -> dict[str, Any]:
    import json

    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"CDP response id={expected_id} timed out")
        raw = ws.recv(timeout=remaining)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        data = json.loads(raw)
        if data.get("id") == expected_id:
            if "error" in data:
                raise RuntimeError(str(data["error"]))
            result = data.get("result")
            return result if isinstance(result, dict) else {}


def _cdp_call(ws: Any, method: str, params: Optional[dict[str, Any]] = None, *, msg_id: int = 1) -> dict[str, Any]:
    import json

    payload: dict[str, Any] = {"id": msg_id, "method": method}
    if params is not None:
        payload["params"] = params
    ws.send(json.dumps(payload))
    return _cdp_recv_result(ws, msg_id)


def _collect_cookies_via_debug_port_sync(port: int) -> list[dict[str, Any]]:
    """
    Read cookies over a fresh Chrome DevTools WebSocket.

    Nodriver's Tab/Connection.send often hangs on Windows; a separate WS to the
    same --remote-debugging-port still answers Storage/Network.getCookies.
    Prefer the browser-level endpoint so we do not steal nodriver's page target.
    """
    from websockets.sync.client import connect as ws_connect

    collected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def _extend(batch: Any) -> None:
        if not batch:
            return
        items = batch if isinstance(batch, list) else []
        for cookie in items:
            if not isinstance(cookie, dict):
                continue
            key = (
                str(cookie.get("name") or ""),
                str(cookie.get("domain") or ""),
                str(cookie.get("path") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            collected.append(cookie)

    def _has_session() -> bool:
        return any(_is_session_cookie_name(str(c.get("name") or "")) for c in collected)

    try:
        with httpx.Client(timeout=3.0) as client:
            version = client.get(f"http://127.0.0.1:{port}/json/version").json()
            try:
                targets = client.get(f"http://127.0.0.1:{port}/json/list").json()
            except Exception:  # noqa: BLE001
                targets = client.get(f"http://127.0.0.1:{port}/json").json()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Chrome /json discovery failed on port %s: %s", port, exc)
        return collected

    msg_id = 1
    browser_ws = version.get("webSocketDebuggerUrl") if isinstance(version, dict) else None
    if isinstance(browser_ws, str) and browser_ws:
        try:
            with ws_connect(browser_ws, open_timeout=3, close_timeout=2, max_size=8 * 1024 * 1024) as ws:
                for method, params in (
                    ("Storage.getCookies", None),
                    ("Network.getAllCookies", None),
                ):
                    msg_id += 1
                    try:
                        result = _cdp_call(ws, method, params, msg_id=msg_id)
                        _extend(result.get("cookies"))
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("%s via browser WS failed: %s", method, exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("browser-level cookie WS failed: %s", exc)

    if _has_session() or not isinstance(targets, list):
        return collected

    # Last resort: attach to a page target (may briefly contend with nodriver).
    for target in targets:
        if not isinstance(target, dict):
            continue
        url = str(target.get("url") or "")
        host = _hostname(url)
        if "cursor." not in host:
            continue
        ws_url = target.get("webSocketDebuggerUrl")
        if not isinstance(ws_url, str) or not ws_url:
            continue
        try:
            with ws_connect(ws_url, open_timeout=3, close_timeout=2, max_size=8 * 1024 * 1024) as ws:
                msg_id += 1
                try:
                    result = _cdp_call(
                        ws,
                        "Network.getCookies",
                        {"urls": list(_COOKIE_URLS)},
                        msg_id=msg_id,
                    )
                    _extend(result.get("cookies"))
                except Exception:  # noqa: BLE001
                    pass
                msg_id += 1
                try:
                    result = _cdp_call(ws, "Storage.getCookies", msg_id=msg_id)
                    _extend(result.get("cookies"))
                except Exception:  # noqa: BLE001
                    pass
                if _has_session():
                    break
        except Exception as exc:  # noqa: BLE001
            logger.debug("page CDP cookie read failed (%s): %s", url[:80], exc)

    return collected


def _pick_live_tab(browser: Any, preferred: Any = None) -> Any:
    """Prefer an open tab currently on cursor.com (real app host, not auth)."""
    tabs: list[Any] = []
    try:
        tabs = [t for t in (getattr(browser, "tabs", None) or []) if t is not None]
    except Exception:  # noqa: BLE001
        tabs = []

    cursor_tabs: list[Any] = []
    open_tabs: list[Any] = []
    for tab in tabs:
        if getattr(tab, "closed", False):
            continue
        open_tabs.append(tab)
        try:
            url = str(getattr(tab, "url", "") or "")
        except Exception:  # noqa: BLE001
            url = ""
        if _is_cursor_app_host(_hostname(url)) or "cursor." in _hostname(url):
            cursor_tabs.append(tab)

    for tab in cursor_tabs:
        try:
            url = str(getattr(tab, "url", "") or "")
        except Exception:  # noqa: BLE001
            url = ""
        if _is_cursor_post_login_url(url):
            return tab
    app_tabs = [
        tab
        for tab in cursor_tabs
        if _is_cursor_app_host(_hostname(str(getattr(tab, "url", "") or "")))
    ]
    if app_tabs:
        return app_tabs[0]
    if cursor_tabs:
        return cursor_tabs[0]
    if preferred is not None and not getattr(preferred, "closed", False):
        return preferred
    return open_tabs[0] if open_tabs else preferred


async def _collect_cookies(
    browser: Any,
    tab: Any = None,
    *,
    debug_port: Optional[int] = None,
) -> list[Any]:
    """Gather cookies — prefer a fresh debug-port WS (nodriver CDP often hangs)."""
    collected: list[Any] = []
    port = debug_port or _browser_debug_port(browser)
    if isinstance(port, int) and port > 0:
        try:
            via_port = await asyncio.to_thread(_collect_cookies_via_debug_port_sync, port)
            if via_port:
                collected.extend(via_port)
                return collected
        except Exception as exc:  # noqa: BLE001
            logger.debug("debug-port cookie read failed: %s", exc)

    # Fallback: nodriver paths (often time out on Windows — keep short).
    live = _pick_live_tab(browser, tab)
    try:
        from nodriver import cdp  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("nodriver.cdp import failed: %s", exc)
        return collected

    connections: list[Any] = []
    if live is not None:
        connections.append(live)
    browser_conn = getattr(browser, "connection", None)
    if browser_conn is not None and browser_conn not in connections:
        connections.append(browser_conn)

    for connection in connections:
        commands: list[Any] = []
        storage_get = getattr(cdp.storage, "get_cookies", None)
        if storage_get is not None:
            commands.append(storage_get())
        get_all = getattr(cdp.network, "get_all_cookies", None)
        if get_all is not None:
            commands.append(get_all())

        for command in commands:
            try:
                batch = await _cdp_send(connection, command, timeout=1.5)
                if batch:
                    if isinstance(batch, dict):
                        batch = batch.get("cookies") or []
                    collected.extend(list(batch))
                    if collected:
                        return collected
            except asyncio.TimeoutError:
                logger.debug("CDP cookie read timed out on %s", type(connection).__name__)
            except Exception as exc:  # noqa: BLE001
                logger.debug("CDP cookie read failed: %s", exc)

    if not collected:
        try:
            jar = await asyncio.wait_for(browser.cookies.get_all(), timeout=1.5)
            if jar:
                collected.extend(list(jar))
        except Exception as exc:  # noqa: BLE001
            logger.debug("browser.cookies.get_all failed/timed out: %s", exc)

    return collected


def _read_session_cookie_from_profile(profile_dir: Path) -> Optional[str]:
    """Best-effort plaintext cookie from Chrome SQLite (often encrypted on Windows)."""
    candidates = [
        profile_dir / "Default" / "Network" / "Cookies",
        profile_dir / "Default" / "Cookies",
    ]
    src = next((path for path in candidates if path.is_file()), None)
    if src is None:
        return None

    tmp_path: Optional[Path] = None
    conn: Any = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            shutil.copy2(src, tmp_path)
            conn = sqlite3.connect(str(tmp_path), timeout=1.0)
        except OSError:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
                tmp_path = None
            uri = f"file:{src.as_posix()}?mode=ro&immutable=1"
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)

        rows = conn.execute(
            "SELECT name, value FROM cookies WHERE lower(name) LIKE '%workos%session%'"
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.debug("profile Cookies SQLite read failed: %s", exc)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    for name, value in rows:
        if not name or value is None:
            continue
        if isinstance(value, bytes):
            if value.startswith((b"v10", b"v11", b"v20")):
                continue
            try:
                value = value.decode("utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                continue
        if not _is_session_cookie_name(str(name)):
            continue
        token = _token_from_cookie_value(str(value))
        if token:
            logger.info("Cursor session cookie recovered from profile SQLite")
            return token
    return None


async def _read_session_cookie(
    browser: Any,
    tab: Any = None,
    *,
    profile_dir: Optional[Path] = None,
    debug_port: Optional[int] = None,
) -> Optional[str]:
    """Return normalized WorkosCursorSessionToken from the NoDriver browser."""
    if browser is None:
        return None

    cookies = await _collect_cookies(browser, tab, debug_port=debug_port)
    for cookie in cookies:
        name, value = _cookie_name_value(cookie)
        if not name or not value:
            continue
        if not _is_session_cookie_name(name):
            continue
        token = _token_from_cookie_value(value)
        if token:
            return token

    if profile_dir is not None:
        return await asyncio.to_thread(_read_session_cookie_from_profile, profile_dir)
    return None


def _cookie_debug_summary(cookies: list[Any]) -> str:
    """Safe summary for logs (names + domains only)."""
    parts: list[str] = []
    for cookie in cookies[:40]:
        name, _value = _cookie_name_value(cookie)
        domain = getattr(cookie, "domain", None)
        if domain is None and isinstance(cookie, dict):
            domain = cookie.get("domain")
        if name:
            parts.append(f"{name}@{domain or '?'}")
    return ", ".join(parts) if parts else "(aucun)"


async def _safe_close_browser(browser: Any, tab: Any, profile_dir: Path) -> None:
    """Gracefully stop Chrome, then delete the ephemeral profile."""
    if tab is not None:
        try:
            await asyncio.wait_for(tab.get("about:blank"), timeout=5.0)
        except Exception:  # noqa: BLE001
            pass

    if browser is not None:
        try:
            import nodriver.cdp.browser as cdp_browser  # type: ignore

            connection = getattr(browser, "connection", None)
            if connection is not None:
                await asyncio.wait_for(connection.send(cdp_browser.close()), timeout=5.0)
                await asyncio.sleep(0.8)
        except Exception as exc:  # noqa: BLE001
            logger.debug("CDP Browser.close: %s", exc)
        try:
            browser.stop()
        except Exception as exc:  # noqa: BLE001
            logger.debug("browser.stop: %s", exc)
        try:
            await asyncio.sleep(0.3)
        except Exception:  # noqa: BLE001
            pass

    try:
        if profile_dir.exists():
            shutil.rmtree(profile_dir, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("profile cleanup: %s", exc)


def _mark_captured(session: LoginSession, token: str) -> None:
    """Store captured token immediately; email is best-effort and must not delay ready."""
    with session._state_lock:
        if session.captured_token:
            return
        session.captured_token = token
        session.captured_email = _email_from_token(token)
        session.finished = True
        session.stop_event.set()

    # Resolve email after marking ready so the UI can proceed without waiting on HTTP.
    if not session.captured_email:
        try:
            email = _email_from_api_sync(token)
        except Exception:  # noqa: BLE001
            email = None
        if email:
            with session._state_lock:
                if session.captured_token == token and not session.captured_email:
                    session.captured_email = email

    logger.info(
        "Cursor session captured via NoDriver (email=%s)",
        session.captured_email or "unknown",
    )


def _maybe_store_intercepted(session: LoginSession, name: Optional[str], value: Optional[str]) -> None:
    if not name or not value or not _is_session_cookie_name(name):
        return
    token = _token_from_cookie_value(value)
    if not token:
        return
    with session._state_lock:
        if not session.intercepted_token:
            session.intercepted_token = token
            logger.info("Cursor session cookie intercepted from network events")


def _headers_to_dict(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    if isinstance(headers, dict):
        return {str(k): str(v) for k, v in headers.items()}
    to_json = getattr(headers, "to_json", None)
    if callable(to_json):
        raw = to_json()
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}
    items = getattr(headers, "items", None)
    if callable(items):
        try:
            return {str(k): str(v) for k, v in items()}
        except Exception:  # noqa: BLE001
            pass
    return {}


def _install_network_interceptors(tab: Any, session: LoginSession) -> None:
    """Capture WorkosCursorSessionToken from live network cookie events."""
    try:
        from nodriver import cdp  # type: ignore
    except Exception:  # noqa: BLE001
        return

    def on_request_extra(event: Any) -> None:
        try:
            for item in getattr(event, "associated_cookies", None) or []:
                cookie = getattr(item, "cookie", item)
                name, value = _cookie_name_value(cookie)
                _maybe_store_intercepted(session, name, value)
        except Exception as exc:  # noqa: BLE001
            logger.debug("request extra cookie intercept failed: %s", exc)

    def on_response_extra(event: Any) -> None:
        try:
            headers = _headers_to_dict(getattr(event, "headers", None))
            for key, raw in headers.items():
                if key.lower() != "set-cookie":
                    continue
                # "WorkosCursorSessionToken=...; Path=/; ..."
                first = str(raw).split(";", 1)[0]
                if "=" not in first:
                    continue
                name, value = first.split("=", 1)
                _maybe_store_intercepted(session, name.strip(), value.strip())
        except Exception as exc:  # noqa: BLE001
            logger.debug("response extra cookie intercept failed: %s", exc)

    try:
        tab.add_handler(cdp.network.RequestWillBeSentExtraInfo, on_request_extra)
        tab.add_handler(cdp.network.ResponseReceivedExtraInfo, on_response_extra)
    except Exception as exc:  # noqa: BLE001
        logger.debug("add_handler failed: %s", exc)


def _mark_error(session: LoginSession, message: str) -> None:
    with session._state_lock:
        if session.captured_token:
            return
        session.error = message
        session.finished = True
        session.stop_event.set()


async def _browser_main(session: LoginSession) -> None:
    """NoDriver lifecycle — runs only inside the dedicated thread loop."""
    browser = None
    tab = None
    last_cookie_debug = 0.0
    dashboard_nudged = False
    try:
        import nodriver as uc
    except ImportError as exc:
        _mark_error(
            session,
            "Le paquet Python « nodriver » est manquant "
            "(pip install nodriver dans l’environnement de l’agent).",
        )
        session.ready_event.set()
        logger.error("nodriver missing: %s", exc)
        return

    try:
        browser = await uc.start(
            headless=False,
            user_data_dir=str(session.profile_dir),
            sandbox=False,
            browser_args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-session-crashed-bubble",
                "--homepage=about:blank",
            ],
        )
        if browser is None:
            raise RuntimeError("nodriver.start() a renvoyé None")

        debug_port = _browser_debug_port(browser)
        with session._state_lock:
            session.debug_port = debug_port
        if debug_port:
            logger.info("Cursor NoDriver debug port=%s", debug_port)

        try:
            await browser.wait(0.35)
        except Exception:  # noqa: BLE001
            pass

        tab = await browser.get(LOGIN_URL)
        try:
            await tab.activate()
        except Exception:  # noqa: BLE001
            pass

        try:
            from nodriver import cdp as _cdp  # type: ignore

            await _cdp_send(tab, _cdp.network.enable())
        except Exception:  # noqa: BLE001
            pass
        _install_network_interceptors(tab, session)

        with session._state_lock:
            session.browser_ready = True
        session.ready_event.set()
        logger.info("Cursor NoDriver browser ready — waiting for session cookie")

        installed_tabs = {id(tab)}

        while not session.stop_event.is_set():
            elapsed = time.monotonic() - session.started_at
            if elapsed > _LOGIN_TIMEOUT_SEC:
                _mark_error(session, "Délai dépassé — réessaie la connexion.")
                break

            tab = _pick_live_tab(browser, tab)
            if tab is not None and id(tab) not in installed_tabs:
                try:
                    from nodriver import cdp as _cdp  # type: ignore

                    await _cdp_send(tab, _cdp.network.enable())
                except Exception:  # noqa: BLE001
                    pass
                _install_network_interceptors(tab, session)
                installed_tabs.add(id(tab))

            with session._state_lock:
                intercepted = session.intercepted_token
                port = session.debug_port
            token = intercepted or await _read_session_cookie(
                browser,
                tab,
                profile_dir=session.profile_dir,
                debug_port=port,
            )
            if token:
                _mark_captured(session, token)
                break

            # Once the user reaches the real app dashboard, nudge a reload so
            # HttpOnly cookies are definitely present in the browser cookie store.
            if not dashboard_nudged and tab is not None:
                try:
                    current_url = str(getattr(tab, "url", "") or "")
                except Exception:  # noqa: BLE001
                    current_url = ""
                if _is_cursor_post_login_url(current_url):
                    dashboard_nudged = True
                    logger.info("Cursor dashboard detected (%s) — refreshing for cookies", current_url)
                    try:
                        await asyncio.wait_for(tab.get(DASHBOARD_URL), timeout=15.0)
                        await asyncio.sleep(1.2)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("dashboard nudge failed: %s", exc)

            now = time.monotonic()
            if now - last_cookie_debug >= _COOKIE_DEBUG_EVERY_SEC:
                last_cookie_debug = now
                try:
                    cookies = await _collect_cookies(browser, tab, debug_port=port)
                    logger.warning(
                        "Cursor login waiting for session cookie (t=%ss) — seen: %s",
                        int(elapsed),
                        _cookie_debug_summary(cookies),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("cookie debug failed: %s", exc)

            try:
                await asyncio.sleep(_POLL_INTERVAL_SEC)
            except asyncio.CancelledError:
                break

    except Exception as exc:  # noqa: BLE001
        logger.exception("NoDriver Cursor login failed")
        _mark_error(session, f"Impossible d’ouvrir Chrome via NoDriver : {exc}")
        session.ready_event.set()
    finally:
        await _safe_close_browser(browser, tab, session.profile_dir)
        with session._state_lock:
            session.finished = True
            session.browser_ready = False


def _browser_thread_entry(session: LoginSession) -> None:
    """Thread target: own asyncio loop for NoDriver."""
    if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:  # noqa: BLE001
            pass
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_browser_main(session))
    except Exception as exc:  # noqa: BLE001
        logger.exception("NoDriver thread crashed: %s", exc)
        _mark_error(session, str(exc))
        session.ready_event.set()
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:  # noqa: BLE001
            pass
        loop.close()


async def _cancel_session(session: LoginSession) -> None:
    """Signal stop and wait briefly for the browser thread to exit."""
    session.stop_event.set()
    thread = session.thread
    if thread and thread.is_alive():
        await asyncio.to_thread(thread.join, 8.0)


async def start_login(cursor_bin: str) -> dict[str, Any]:
    """
    Open an isolated Chromium via NoDriver (background thread).

    Args:
        cursor_bin: Unused (kept for worker API compatibility).
    """
    del cursor_bin

    with _sessions_lock:
        existing_ids = list(_sessions.keys())
    for login_id in existing_ids:
        await cancel_login(login_id)

    login_id = str(uuid.uuid4())
    profile_dir = _profiles_root() / login_id
    profile_dir.mkdir(parents=True, exist_ok=True)

    session = LoginSession(id=login_id, profile_dir=profile_dir)
    with _sessions_lock:
        _sessions[login_id] = session

    thread = threading.Thread(
        target=_browser_thread_entry,
        args=(session,),
        name=f"cursor-nodriver-{login_id[:8]}",
        daemon=True,
    )
    session.thread = thread
    thread.start()

    # Wait until Chrome is up (or failed) without blocking the agent loop hard.
    ready = await asyncio.to_thread(
        session.ready_event.wait,
        _BROWSER_START_TIMEOUT_SEC,
    )
    with session._state_lock:
        error = session.error
        browser_ready = session.browser_ready
        captured = session.captured_token

    if not ready and not browser_ready and not captured:
        await cancel_login(login_id)
        return {
            "login_id": None,
            "login_url": LOGIN_URL,
            "status": "error",
            "mode": "browser",
            "error": "Délai dépassé en ouvrant Chrome (NoDriver).",
        }

    if error and not captured:
        with _sessions_lock:
            _sessions.pop(login_id, None)
        return {
            "login_id": None,
            "login_url": LOGIN_URL,
            "status": "error",
            "mode": "browser",
            "error": error,
        }

    if captured:
        return {
            "login_id": login_id,
            "login_url": LOGIN_URL,
            "status": "ready",
            "mode": "browser",
            "session_token": session.captured_token,
            "email": session.captured_email,
            "restored_machine_session": False,
        }

    return {
        "login_id": login_id,
        "login_url": LOGIN_URL,
        "status": "pending",
        "mode": "browser",
        "note": None,
        "warning": None,
    }


def _snapshot(session: LoginSession) -> dict[str, Any]:
    with session._state_lock:
        return {
            "captured_token": session.captured_token,
            "captured_email": session.captured_email,
            "error": session.error,
            "finished": session.finished,
            "browser_ready": session.browser_ready,
            "elapsed_seconds": int(time.monotonic() - session.started_at),
        }


async def poll_login(login_id: str) -> dict[str, Any]:
    """Check whether the background NoDriver thread captured a cookie."""
    with _sessions_lock:
        session = _sessions.get(login_id)
    if session is None:
        return {"status": "error", "error": "Session de login inconnue ou expirée"}

    snap = _snapshot(session)
    if snap["captured_token"]:
        return {
            "status": "ready",
            "session_token": snap["captured_token"],
            "email": snap["captured_email"],
            "restored_machine_session": False,
        }
    if snap["error"] and snap["finished"]:
        return {"status": "error", "error": snap["error"]}

    return {
        "status": "pending",
        "login_url": LOGIN_URL,
        "mode": "browser",
        "elapsed_seconds": snap["elapsed_seconds"],
        "browser_ready": snap["browser_ready"],
    }


async def complete_login(login_id: str) -> dict[str, Any]:
    """
    Manual confirm — usually unnecessary (auto-capture).

    Gives the cookie a short extra window to appear, then reports clearly.
    """
    result = await poll_login(login_id)
    if result.get("status") == "ready":
        return result

    with _sessions_lock:
        session = _sessions.get(login_id)
    if session is None:
        return {"status": "error", "error": "Session de login inconnue ou expirée"}

    # Wait up to ~8s for the browser thread to finish capturing.
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        snap = _snapshot(session)
        if snap["captured_token"]:
            return {
                "status": "ready",
                "session_token": snap["captured_token"],
                "email": snap["captured_email"],
                "restored_machine_session": False,
            }
        if snap["error"] and snap["finished"]:
            return {"status": "error", "error": snap["error"]}
        await asyncio.sleep(0.4)

    return {
        "status": "error",
        "error": (
            "Cookie introuvable. Connecte-toi bien dans la fenêtre Chrome NightForge, "
            "puis attends quelques secondes (capture auto) ou réessaie."
        ),
    }


async def cancel_login(login_id: str) -> dict[str, Any]:
    """Cancel capture and close the NoDriver browser thread."""
    with _sessions_lock:
        session = _sessions.pop(login_id, None)
    if session is None:
        return {"status": "ok"}
    await _cancel_session(session)
    return {"status": "ok", "restored_machine_session": False}
