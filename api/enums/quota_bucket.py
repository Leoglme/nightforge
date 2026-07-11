"""
Claude Max usage buckets (rolling windows).
"""
from enum import Enum


class QuotaBucket(str, Enum):
    """
    The Claude Max usage buckets tracked for planning.

    Attributes:
        FIVE_HOUR: Rolling 5-hour window (all models).
        SEVEN_DAY: Rolling 7-day window (all models).
        SEVEN_DAY_OPUS: Rolling 7-day Opus-only window.
        SEVEN_DAY_OAUTH_APPS: Rolling 7-day Claude Code / MCP traffic window.
    """

    FIVE_HOUR = "five_hour"
    SEVEN_DAY = "seven_day"
    SEVEN_DAY_OPUS = "seven_day_opus"
    SEVEN_DAY_OAUTH_APPS = "seven_day_oauth_apps"
