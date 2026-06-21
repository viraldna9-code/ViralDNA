"""
Ad-Friendly Check v3.0 — VDNA 3.0 Port
Advertiser-friendly content analysis for monetization optimization.
Uses existing AdFriendlyChecker from ad_friendly_check.py.
Ported from old pipeline's AdFriendlyCheckAgent.
"""
import os, sys

_MODULES_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)

from ad_friendly_check import AdFriendlyChecker
from datetime import datetime


class AdFriendlyCheckV3:
    """
    Inline ad-friendly content check: verifies advertiser-friendly status
    for broader audience reach and monetization.
    """

    def __init__(self, *args, **kwargs):
        self.checker = AdFriendlyChecker()

    def check_content(self, title: str, description: str = "", script: str = "", tags: list = None) -> dict:
        """Run ad-friendly check. Returns score dict."""
        try:
            result = self.checker.check_content(
                title=title,
                description=description,
                script=script,
                tags=tags or [],
            )
            return result
        except Exception as e:
            return {
                "score": 75,
                "risk_level": "medium",
                "monetization_expectation": "Limited or no ads",
                "recommendations": [f"Check error: {str(e)[:80]}"],
                "checked_at": datetime.now().isoformat(),
            }

    def execute(self, state):
        return state
