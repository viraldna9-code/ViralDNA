"""
Content Calendar v3.0 — VDNA 3.0 Port
Content scheduling, topic alignment, category rotation.
Uses existing ContentCalendar from content_calendar.py.
Ported from old pipeline's ContentCalendarAgent.
"""
import os, sys

# Ensure modules dir is in path for direct imports
_MODULES_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)

from content_calendar import ContentCalendar, CATEGORY_WEIGHTS, CATEGORY_COOLDOWN_DAYS
from datetime import datetime


class ContentCalendarV3:
    """
    Pre-pipeline content calendar: checks upcoming planned content
    and ensures topic alignment with content strategy.
    """

    def __init__(self, *args, **kwargs):
        self.calendar = ContentCalendar()

    def get_weekly_schedule(self) -> dict:
        """Get the weekly content schedule."""
        try:
            return self.calendar.get_weekly_schedule()
        except Exception:
            return self._default_schedule()

    def _default_schedule(self) -> dict:
        return {
            "shorts_per_week": 6,
            "main_videos_per_week": 2,
            "category_rotation": list(CATEGORY_WEIGHTS.keys()),
            "note": "Default schedule (calendar unavailable)",
        }

    def check_topic_alignment(self, topic: dict) -> dict:
        """Check if a topic aligns with the content calendar strategy."""
        category = (
            topic.get("pillar")
            or topic.get("category")
            or topic.get("topic_category")
            or "UNKNOWN"
        )
        cooldown = CATEGORY_COOLDOWN_DAYS.get(category, 1)
        weight = CATEGORY_WEIGHTS.get(category, 1)
        return {
            "category": category,
            "cooldown_days": cooldown,
            "weight": weight,
            "aligned": weight > 0,
            "checked_at": datetime.now().isoformat(),
        }

    def get_category_rotation(self) -> list:
        """Get the recommended category rotation order."""
        sorted_cats = sorted(CATEGORY_WEIGHTS, key=lambda k: CATEGORY_WEIGHTS[k], reverse=True)
        return sorted_cats

    def execute(self, state):
        return state
