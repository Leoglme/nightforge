"""
AI provider identifiers for NightForge runs (Claude Code or Cursor Agent).
"""
from enum import Enum


class AiProvider(str, Enum):
    """Which local CLI executes a prompt."""

    CLAUDE = "claude"
    CURSOR = "cursor"
