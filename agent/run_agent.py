"""
PyInstaller entry point for the NightForge agent sidecar.

PyInstaller cannot run ``nightforge_agent/__main__.py`` with relative imports — use this
script as the onefile bundle entry instead of ``python -m nightforge_agent``.
"""
from __future__ import annotations

import sys


def _oauth_token_mode() -> bool:
    return len(sys.argv) >= 2 and sys.argv[1] in ("--oauth-token", "oauth-token")


if __name__ == "__main__":
    if _oauth_token_mode():
        from nightforge_agent.oauth_credentials import ensure_valid_oauth_sync

        token = ensure_valid_oauth_sync(auto_repair=True)
        if not token:
            raise SystemExit(1)
        print(token, end="")
        raise SystemExit(0)

    from nightforge_agent.__main__ import main

    main()
