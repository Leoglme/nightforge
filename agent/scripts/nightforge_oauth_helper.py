#!/usr/bin/env python3
"""
Legacy Claude Code apiKeyHelper entry point.

NightForge no longer configures ``apiKeyHelper`` globally. The agent injects OAuth
tokens per subprocess instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_ROOT))

from nightforge_agent.oauth_credentials import ensure_valid_oauth_sync  # noqa: E402


def main() -> int:
    token = ensure_valid_oauth_sync(auto_repair=True)
    if not token:
        return 1
    print(token, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
