"""
Ensure only one NightForge agent worker runs per Windows user session.
"""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

_MUTEX_NAME = "Local\\NightForgeAgentSingleton"
# Keep the mutex handle alive for the process lifetime (do not let it go out of scope).
_MUTEX_HANDLE = None


def acquire_singleton_or_exit() -> None:
    """
    Exit quietly when another agent instance already holds the mutex.
    """
    if sys.platform != "win32":
        return

    global _MUTEX_HANDLE
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        # bInitialOwner=True so we own the mutex immediately; CreateMutex is atomic.
        handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
        last_error = kernel32.GetLastError()
        if not handle:
            return
        if last_error == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            message = (
                "Another NightForge agent is already running — exiting duplicate "
                "(kill orphan nightforge-agent.exe if the machine stays offline)"
            )
            # Logging may not be configured yet (called before basicConfig).
            print(message, file=sys.stderr, flush=True)
            logger.info(message)
            raise SystemExit(0)
        _MUTEX_HANDLE = handle
    except OSError as exc:
        logger.debug("Could not create agent singleton mutex: %s", exc)
