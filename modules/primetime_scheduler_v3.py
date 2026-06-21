"""
Primetime Scheduler v3.0 — VDNA 3.0 Port
Optimal upload time scheduling based on time of day, day of week, historical performance.
Ported from old pipeline's PrimetimeSchedulerAgent.
"""
import os, sys
from datetime import datetime
from zoneinfo import ZoneInfo

_MODULES_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)

from upload_time_optimizer import UploadTimeOptimizer


class PrimetimeScheduler:
    """
    Pre-pipeline scheduler: decides run mode based on time of day,
    day of week, and historical performance from the ledger.
    """

    # IST hours for different modes
    PRIMETIME_HOURS = [16, 17, 18, 19, 20]  # 4PM-8PM IST
    QUIET_HOURS = [0, 1, 2, 3, 4, 5]         # Midnight-5AM

    def __init__(self, *args, **kwargs):
        self.optimizer = UploadTimeOptimizer()
        self.adjustments = {}

    def get_run_mode(self) -> dict:
        """Determine the optimal run mode based on current time."""
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
        hour = now_ist.hour

        if hour in self.PRIMETIME_HOURS:
            mode = "primetime"
            lookback_hours = 12
        elif hour in self.QUIET_HOURS:
            mode = "quiet"
            lookback_hours = 6
        else:
            mode = "normal"
            lookback_hours = 6

        return {
            "mode": mode,
            "lookback_hours": lookback_hours,
            "hour_ist": hour,
            "scheduled_at": now_ist.isoformat(),
            "is_primetime": mode == "primetime",
            "is_quiet": mode == "quiet",
        }

    def get_upload_schedule(self) -> dict:
        """Get the optimal upload schedule."""
        try:
            schedule = self.optimizer.get_optimal_upload_time()
            shorts_schedule = self.optimizer.get_shorts_schedule(
                schedule.get("recommended_time_ist", "18:00")
            )
            return {
                "main_upload": schedule,
                "shorts_schedule": shorts_schedule,
                "source": "upload_time_optimizer",
            }
        except Exception:
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
            hour = now.hour
            if hour in self.PRIMETIME_HOURS:
                recommended = "18:00"
                window = "primetime"
            elif hour in self.QUIET_HOURS:
                recommended = "09:00"
                window = "morning"
            else:
                recommended = "14:00"
                window = "afternoon"
            return {
                "main_upload": {
                    "recommended_time_ist": recommended,
                    "window_name": window,
                    "final_score": 50,
                },
                "shorts_schedule": [],
                "source": "default_fallback",
            }

    def execute(self, state):
        return state
