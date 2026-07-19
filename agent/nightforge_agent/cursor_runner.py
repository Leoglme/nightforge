"""
Cursor Agent CLI runner — headless `agent -p` for NightForge overnight / queue runs.

If the CLI is missing, NightForge installs it silently via the official Cursor
installer, then retries the prompt.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import AsyncIterator, Optional

logger = logging.getLogger(__name__)

#: Serialize auto-install so parallel prompts do not race the installer.
_install_lock = asyncio.Lock()
_install_attempted = False


class CursorBinNotFoundError(FileNotFoundError):
    """Raised when the Cursor Agent CLI binary cannot be resolved."""


class CursorInstallError(RuntimeError):
    """Raised when the silent Cursor CLI install fails."""


def _windows_install_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "cursor-agent"


def _windows_install_candidates() -> list[str]:
    """
    Well-known Windows install locations for the Cursor Agent CLI.

    The official installer drops launchers under ``%LOCALAPPDATA%\\cursor-agent``
    and may not refresh PATH for an already-running NightForge agent process.
    """
    root = _windows_install_dir()
    names = ("agent.cmd", "agent.exe", "cursor-agent.cmd", "cursor-agent.exe", "agent.ps1")
    return [str(root / name) for name in names]


def _unix_install_candidates() -> list[str]:
    """Common Unix install locations for the Cursor Agent CLI."""
    home = Path.home()
    names = ("agent", "cursor-agent")
    roots = [
        home / ".local" / "bin",
        home / ".cursor" / "bin",
        Path("/usr/local/bin"),
    ]
    out: list[str] = []
    for root in roots:
        for name in names:
            out.append(str(root / name))
    return out


def _augment_process_path() -> None:
    """Make known Cursor install dirs visible to this process (and children)."""
    extras: list[str] = []
    if os.name == "nt":
        extras.append(str(_windows_install_dir()))
    else:
        extras.append(str(Path.home() / ".local" / "bin"))
    path = os.environ.get("PATH", "")
    parts = [p for p in extras if p and p.lower() not in path.lower()]
    if parts:
        os.environ["PATH"] = os.pathsep.join(parts + ([path] if path else []))


def try_resolve_cursor_bin(configured: str) -> Optional[str]:
    """
    Resolve the Cursor Agent CLI without raising.

    Args:
        configured: Value from ``NF_CURSOR_BIN`` (default ``agent``).

    Returns:
        Absolute path or command name, or None when missing.
    """
    _augment_process_path()
    candidates = [configured]
    if os.name == "nt":
        if not configured.lower().endswith((".cmd", ".exe", ".bat", ".ps1")):
            candidates.extend(
                [
                    f"{configured}.cmd",
                    f"{configured}.exe",
                    "agent.cmd",
                    "agent.exe",
                    "cursor-agent.cmd",
                    "cursor-agent.exe",
                    "cursor-agent",
                ]
            )
        candidates.extend(_windows_install_candidates())
    else:
        candidates.extend(["cursor-agent", "agent"])
        candidates.extend(_unix_install_candidates())

    for name in candidates:
        if os.path.isfile(name):
            return name
        found = shutil.which(name)
        if found:
            return found
    return None


def resolve_cursor_bin(configured: str) -> str:
    """
    Resolve the Cursor Agent CLI binary on the current platform.

    Args:
        configured: Value from ``NF_CURSOR_BIN`` (default ``agent``).

    Returns:
        Absolute path (preferred) or command name suitable for ``create_subprocess_exec``.

    Raises:
        CursorBinNotFoundError: When no usable binary can be found.
    """
    found = try_resolve_cursor_bin(configured)
    if found:
        return found
    raise CursorBinNotFoundError(
        f"CLI Cursor Agent introuvable (cherché: {configured!r})."
    )


async def install_cursor_cli(*, timeout: float = 300.0) -> None:
    """
    Silently install the official Cursor Agent CLI for the current OS.

    Args:
        timeout: Max seconds to wait for the installer.

    Raises:
        CursorInstallError: When the installer exits non-zero or times out.
    """
    global _install_attempted

    async with _install_lock:
        # Another waiter may have finished installing while we waited for the lock.
        if try_resolve_cursor_bin("agent"):
            _install_attempted = True
            return

        if os.name == "nt":
            command = (
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "irm 'https://cursor.com/install?win32=true' | iex",
            )
        else:
            command = (
                "bash",
                "-lc",
                "curl https://cursor.com/install -fsS | bash",
            )

        logger.info("Installing Cursor Agent CLI via official installer…")
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError as exc:
            raise CursorInstallError(
                f"Impossible de lancer l'installateur Cursor: {exc}"
            ) from exc

        assert process.stdout is not None
        output_chunks: list[str] = []
        try:
            while True:
                raw = await asyncio.wait_for(process.stdout.readline(), timeout=timeout)
                if not raw:
                    break
                line = raw.decode(errors="replace").rstrip()
                if line:
                    output_chunks.append(line)
                    logger.info("cursor-install: %s", line)
            exit_code = await asyncio.wait_for(process.wait(), timeout=30.0)
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise CursorInstallError(
                f"Installation du CLI Cursor Agent expirée après {int(timeout)}s"
            ) from exc

        _install_attempted = True
        _augment_process_path()

        if exit_code != 0:
            tail = "\n".join(output_chunks[-8:]) if output_chunks else "(aucune sortie)"
            raise CursorInstallError(
                f"Installateur Cursor a échoué (exit {exit_code}).\n{tail}"
            )

        # Brief settle time — antivirus / filesystem may lag behind the installer.
        for _ in range(10):
            if try_resolve_cursor_bin("agent"):
                return
            await asyncio.sleep(0.5)

        raise CursorInstallError(
            "Installateur Cursor terminé, mais `agent` reste introuvable. "
            f"Vérifie {_windows_install_dir() if os.name == 'nt' else '~/.local/bin'}."
        )


async def ensure_cursor_bin(configured: str) -> AsyncIterator[str]:
    """
    Resolve the Cursor CLI, auto-installing it once when missing.

    Yields:
        Human-readable progress lines, then nothing else — call
        ``resolve_cursor_bin`` after the iterator finishes.
    """
    if try_resolve_cursor_bin(configured):
        return

    yield "CLI Cursor Agent manquant — installation silencieuse en cours…"
    try:
        await install_cursor_cli()
    except CursorInstallError as exc:
        logger.error("Cursor CLI install failed: %s", exc)
        raise
    yield "CLI Cursor Agent installé — reprise du prompt…"


def build_cursor_model_arg(
    model: Optional[str],
    *,
    effort: Optional[str] = None,
    fast_mode: bool = False,
) -> Optional[str]:
    """
    Build the ``--model`` value for Cursor CLI (params in bracket syntax when needed).

    Args:
        model: Base model id (e.g. ``grok-4.5``, ``composer-2.5``, ``opus``).
        effort: Optional effort / thinking level.
        fast_mode: Whether to request the fast variant.

    Returns:
        Model string for ``--model``, or None to omit the flag.
    """
    if not model:
        return None
    params: list[str] = []
    if fast_mode:
        params.append("fast=true")
    else:
        # Prefer non-fast when the CLI supports it
        if model.startswith("composer") or model.startswith("grok") or model in (
            "opus",
            "fable",
            "sonnet",
        ):
            params.append("fast=false")
    if effort and model != "composer-2.5":
        # Map NightForge effort labels to Cursor thinking/effort params when useful
        params.append(f"effort={effort}")
    if not params:
        return model
    return f"{model}[{','.join(params)}]"


def normalize_cursor_auth_token(raw: str) -> str:
    """
    Normalize a vault / IDE token for ``CURSOR_AUTH_TOKEN`` / ``--auth-token``.

    Workos cookies look like ``userId::jwt`` (or URL-encoded ``%3A%3A``). The CLI
    expects the JWT access token itself.
    """
    token = raw.strip().replace("%3A%3A", "::")
    if "::" in token:
        token = token.split("::")[-1].strip()
    return token


def resolve_cursor_auth(
    *,
    api_key: Optional[str] = None,
    session_token: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], str]:
    """
    Pick API key / auth token for the Cursor CLI, falling back to the local IDE session.

    Returns:
        ``(api_key, auth_token, source_label)``
    """
    if api_key and api_key.strip():
        return api_key.strip(), None, "api-key"
    if session_token and session_token.strip():
        return None, normalize_cursor_auth_token(session_token), "vault"
    try:
        from . import cursor_usage_reader

        local_token, local_email = cursor_usage_reader.export_local_session()
    except Exception:  # noqa: BLE001
        local_token, local_email = None, None
    if local_token and local_token.strip():
        label = f"IDE locale ({local_email})" if local_email else "IDE locale"
        return None, normalize_cursor_auth_token(local_token), label
    return None, None, "none"


def cursor_subprocess_env(
    *,
    api_key: Optional[str] = None,
    session_token: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> dict[str, str]:
    """
    Build env for a Cursor Agent subprocess, optionally scoped to one account.

    Official CLI auth (see Cursor docs):
    - ``CURSOR_API_KEY`` / ``--api-key``
    - ``CURSOR_AUTH_TOKEN`` / ``--auth-token`` (session / IDE access token)

    Args:
        api_key: Optional user/service API key.
        session_token: Optional vault session (normalized to auth token when needed).
        auth_token: Optional pre-normalized auth token (preferred over session_token).

    Returns:
        Environment mapping for ``create_subprocess_exec``.
    """
    env = os.environ.copy()
    # Ensure the official install dir is visible even if the agent started before install.
    if os.name == "nt":
        agent_dir = str(_windows_install_dir())
        path = env.get("PATH", "")
        if agent_dir.lower() not in path.lower():
            env["PATH"] = f"{agent_dir};{path}" if path else agent_dir
    else:
        local_bin = str(Path.home() / ".local" / "bin")
        path = env.get("PATH", "")
        if local_bin not in path:
            env["PATH"] = f"{local_bin}:{path}" if path else local_bin

    # Clear stale auth so a machine-level env var cannot override vault/IDE credentials.
    env.pop("CURSOR_API_KEY", None)
    env.pop("CURSOR_AUTH_TOKEN", None)
    env.pop("CURSOR_SESSION_TOKEN", None)

    resolved_key, resolved_auth, _source = resolve_cursor_auth(
        api_key=api_key,
        session_token=session_token,
    )
    if auth_token and auth_token.strip():
        resolved_auth = normalize_cursor_auth_token(auth_token)
        resolved_key = None

    if resolved_key:
        env["CURSOR_API_KEY"] = resolved_key
    elif resolved_auth:
        env["CURSOR_AUTH_TOKEN"] = resolved_auth
    return env


async def run_prompt(
    cursor_bin: str,
    cwd: str,
    prompt: str,
    model: Optional[str] = None,
    effort: Optional[str] = None,
    fast_mode: bool = False,
    api_key: Optional[str] = None,
    session_token: Optional[str] = None,
    *,
    _allow_install: bool = True,
    _allow_local_auth_fallback: bool = True,
) -> AsyncIterator[str]:
    """
    Run a prompt through Cursor Agent in headless mode, yielding output lines.

    If the CLI is missing, installs it silently then runs the prompt.
    Auth uses vault API key / session token, else the local Cursor IDE session
    (``CURSOR_AUTH_TOKEN``).

    Final sentinel: ``__NF_RESULT__:<exit>:<quota_hit>:<reset_iso>:<session_id>``
    (quota_hit always 0 for Cursor — Claude Max planner does not apply).

    Args:
        cursor_bin: Path or name of the Cursor Agent CLI.
        cwd: Workspace directory (project clone).
        prompt: The prompt to send.
        model: Optional model id.
        effort: Optional effort level.
        fast_mode: Fast variant toggle.
        api_key: Optional per-account API key.
        session_token: Optional per-account session token.
        _allow_install: Internal — False disables a second install attempt.
        _allow_local_auth_fallback: Internal — retry once with IDE session on auth failure.

    Yields:
        Progress / output lines, then a final sentinel line.
    """
    if _allow_install:
        async for status in ensure_cursor_bin(cursor_bin):
            yield status

    try:
        binary = resolve_cursor_bin(cursor_bin)
    except CursorBinNotFoundError as exc:
        raise CursorInstallError(str(exc)) from exc

    resolved_key, resolved_auth, auth_source = resolve_cursor_auth(
        api_key=api_key,
        session_token=session_token,
    )
    if auth_source == "none":
        yield (
            "Aucune auth Cursor trouvée (vault / IDE). "
            "Connecte Cursor IDE ou ajoute un compte dans NightForge."
        )
    elif auth_source.startswith("IDE"):
        yield f"Auth Cursor silencieuse via {auth_source}"

    model_arg = build_cursor_model_arg(model, effort=effort, fast_mode=fast_mode)
    env = cursor_subprocess_env(api_key=resolved_key, auth_token=resolved_auth)

    # PowerShell launchers (.ps1) must go through powershell.exe — CreateProcess
    # cannot execute .ps1 directly.
    if binary.lower().endswith(".ps1"):
        args = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            binary,
            "-p",
            "--force",
            "--trust",
            "--approve-mcps",
            "--workspace",
            cwd,
        ]
    else:
        args = [
            binary,
            "-p",
            "--force",
            "--trust",
            "--approve-mcps",
            "--workspace",
            cwd,
        ]
    if model_arg:
        args += ["--model", model_arg]
    if resolved_key:
        args += ["--api-key", resolved_key]
    elif resolved_auth:
        args += ["--auth-token", resolved_auth]
    args.append(prompt)

    logger.info(
        "Spawning Cursor Agent: %s (cwd=%s auth=%s)",
        " ".join(args[:8]),
        cwd,
        auth_source,
    )
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError as exc:
        if _allow_install:
            yield "CLI Cursor Agent introuvable au lancement — installation silencieuse…"
            await install_cursor_cli()
            async for line in run_prompt(
                cursor_bin,
                cwd,
                prompt,
                model=model,
                effort=effort,
                fast_mode=fast_mode,
                api_key=api_key,
                session_token=session_token,
                _allow_install=False,
                _allow_local_auth_fallback=_allow_local_auth_fallback,
            ):
                yield line
            return
        raise CursorBinNotFoundError(
            f"Impossible de lancer le CLI Cursor ({binary!r}): {exc}"
        ) from exc

    assert process.stdout is not None
    collected: list[str] = []
    async for raw in process.stdout:
        line = raw.decode(errors="replace").rstrip("\n")
        collected.append(line)
        yield line

    exit_code = await process.wait()

    auth_failed = exit_code != 0 and any(
        "Authentication required" in line or "not authenticated" in line.lower()
        for line in collected
    )
    if (
        auth_failed
        and _allow_local_auth_fallback
        and auth_source in ("vault", "api-key")
    ):
        yield "Auth vault refusée par le CLI — nouvelle tentative avec la session Cursor IDE…"
        async for line in run_prompt(
            cursor_bin,
            cwd,
            prompt,
            model=model,
            effort=effort,
            fast_mode=fast_mode,
            api_key=None,
            session_token=None,
            _allow_install=False,
            _allow_local_auth_fallback=False,
        ):
            yield line
        return

    # Cursor has no Claude-style quota_hit / session id in this path yet.
    yield f"__NF_RESULT__:{exit_code}:0::"
