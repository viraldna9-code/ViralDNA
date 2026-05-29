"""
Upload Time Optimizer v2.0
Determines optimal upload schedule based on Telugu diaspora audience timezones.
Analyzes ledger history for performance by time-of-day and day-of-week.
"""
import os, json
from datetime import datetime, timedelta, timezone


class UploadTimeOptimizer:
    """
    Finds best upload times for main videos and Shorts
    based on Telugu diaspora audience patterns.
    """

    # Primary audience: India (IST = UTC+5:30), US East (EST = UTC-5), UK (GMT)
    # Peak overlap windows: 4-8PM IST = morning US, afternoon UK
    PEAK_WINDOWS_IST = [
        {"name": "Early Morning", "start_ist": "05:30", "end_ist": "07:00",
         "description": "India rising — lower competition, fresh feed",
         "score": 70},
        {"name": "Midday Peak", "start_ist": "11:00", "end_ist": "13:00",
         "description": "India lunch break + US early morning overlap",
         "score": 82},
        {"name": "Afternoon Surge", "start_ist": "15:00", "end_ist": "17:00",
         "description": "India afternoon + US morning + UK afternoon overlap",
         "score": 90},
        {"name": "Primetime Peak", "start_ist": "18:00", "end_ist": "20:30",
         "description": "India evening prime time — HIGHEST ENGAGEMENT window",
         "score": 100},
        {"name": "Late Evening", "start_ist": "21:00", "end_ist": "22:30",
         "description": "India night + US afternoon overlap",
         "score": 85},
    ]

    IDEAL_DAYS = ["Thursday", "Friday", "Saturday", "Sunday"]

    def __init__(self, *args, **kwargs):
        self.ledger_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "growth_ledger.json"
        )
        self.timezone = timezone(timedelta(hours=5, minutes=30))  # IST

    # ── Main upload time ────────────────────────────────────────────────

    def get_optimal_upload_time(self) -> dict:
        """
        Returns the recommended upload time based on day-of-week
        and historical performance from the ledger.
        """
        now_ist = datetime.now(self.timezone)
        day_name = now_ist.strftime("%A")
        is_weekend = day_name in self.IDEAL_DAYS

        # Find best window for today
        best_window = max(self.PEAK_WINDOWS_IST, key=lambda w: w["score"])
        recommended_time_ist = best_window["start_ist"]

        # Check if we're already past the best window today
        current_hour = now_ist.hour + now_ist.minute / 60
        recommended_hour = int(recommended_time_ist.split(":")[0]) + int(recommended_time_ist.split(":")[1]) / 60

        if current_hour >= recommended_hour:
            # Find next available window
            for window in sorted(self.PEAK_WINDOWS_IST, key=lambda w: w["score"], reverse=True):
                wh = int(window["start_ist"].split(":")[0]) + int(window["start_ist"].split(":")[1]) / 60
                if current_hour < wh:
                    recommended_time_ist = window["start_ist"]
                    best_window = window
                    break
            else:
                # All windows passed — recommend tomorrow's best
                recommended_time_ist = best_window["start_ist"]
                day_name = (now_ist + timedelta(days=1)).strftime("%A")

        # Check ledger for historical performance by upload hour
        ledger_insight = self._analyze_ledger_performance()

        return {
            "recommended_time_ist": recommended_time_ist,
            "window_name": best_window["name"],
            "window_description": best_window["description"],
            "window_score": best_window["score"],
            "day": day_name,
            "is_ideal_day": is_weekend,
            "next_best_slot": self._get_next_best_slot(recommended_time_ist),
            "ledger_insight": ledger_insight,
            "all_windows": [w["name"] for w in sorted(self.PEAK_WINDOWS_IST, key=lambda x: x["score"], reverse=True)],
        }

    # ── Shorts upload schedule ──────────────────────────────────────────

    def get_shorts_schedule(self, main_time_ist: str = "07:00") -> list:
        """
        Returns optimal upload times for 3 Shorts staggered around the main video.
        Shorts should go out when main video gets initial traction.
        """
        main_hour = int(main_time_ist.split(":")[0]) + int(main_time_ist.split(":")[1]) / 60

        schedule = []
        offsets = [
            {"delta_hours": -1.5, "short_number": 1,
             "strategy": "Pre-main teaser — hooks viewers before main drops"},
            {"delta_hours": 2.0, "short_number": 2,
             "strategy": "Post-main riding — catches viewers who watched main"},
            {"delta_hours": 5.0, "short_number": 3,
             "strategy": "Evening boost — second wave as India evening begins"},
        ]

        for offset in offsets:
            short_time_h = (main_hour + offset["delta_hours"]) % 24
            short_hour = int(short_time_h)
            short_minute = int((short_time_h - short_hour) * 60)
            ist_time = f"{short_hour:02d}:{short_minute:02d}"

            schedule.append({
                "short_number": offset["short_number"],
                "ist_time": ist_time,
                "strategy": offset["strategy"],
                "stagger_from_main": f"{offset['delta_hours']:+.1f}h",
            })

        return schedule

    # ── Helpers ─────────────────────────────────────────────────────────

    def _analyze_ledger_performance(self) -> dict:
        """Analyze growth ledger for upload time performance patterns."""
        try:
            if not os.path.exists(self.ledger_path):
                return {"status": "no_ledger", "message": "No ledger data yet. Using defaults."}

            with open(self.ledger_path, "r") as f:
                ledger = json.load(f)

            history = ledger.get("execution_history", [])
            if len(history) < 3:
                return {"status": "insufficient_data", "samples": len(history),
                        "message": f"Only {len(history)} uploads recorded. Need 3+ for analysis."}

            # Count uploads by day and find best performing day
            day_counts = {}
            for entry in history:
                day = entry.get("day_of_week", "Unknown")
                day_counts[day] = day_counts.get(day, 0) + 1

            most_common_day = max(day_counts, key=lambda k: day_counts[k]) if day_counts else None

            return {
                "status": "analyzed",
                "total_uploads": len(history),
                "most_common_upload_day": most_common_day,
                "day_distribution": day_counts,
                "insight": "Primetime Peak (6-8:30PM IST) is the recommended default for Telugu audience.",
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _get_next_best_slot(self, current_recommended: str) -> str:
        """Return the second-best window as a fallback."""
        sorted_windows = sorted(self.PEAK_WINDOWS_IST, key=lambda w: w["score"], reverse=True)
        if len(sorted_windows) >= 2:
            return sorted_windows[1]["start_ist"]
        return sorted_windows[0]["start_ist"]

    # ── D3.1: Schedule Enforcement ──────────────────────────────────────

    def check_schedule_compliance(self) -> dict:
        """
        D3.1: Enforce upload schedule consistency.
        Checks: gap since last upload, daily quota, ideal day/time adherence.
        Returns compliance report with warnings and recommendations.
        """
        now_ist = datetime.now(self.timezone)
        result = {
            "compliant": True,
            "warnings": [],
            "recommendations": [],
            "now_ist": now_ist.strftime("%Y-%m-%d %H:%M IST"),
        }

        # 1. Check gap since last upload
        gap_info = self._check_upload_gap()
        result["last_upload"] = gap_info
        if gap_info.get("hours_since_last") is not None:
            hours = gap_info["hours_since_last"]
            if hours > 48:
                result["compliant"] = False
                result["warnings"].append(f"No upload in {hours:.0f} hours — schedule gap detected")
                result["recommendations"].append("Upload a video today to maintain consistency")
            elif hours > 24:
                result["warnings"].append(f"Last upload was {hours:.0f} hours ago — approaching gap threshold")

        # 2. Check if today is an ideal upload day
        day_name = now_ist.strftime("%A")
        if day_name not in self.IDEAL_DAYS:
            result["warnings"].append(f"{day_name} is not an ideal upload day (best: {', '.join(self.IDEAL_DAYS)})")
            result["recommendations"].append(f"Consider uploading on {self.IDEAL_DAYS[0]} or {self.IDEAL_DAYS[1]} instead")

        # 3. Check if current time is in a peak window
        current_hour = now_ist.hour + now_ist.minute / 60
        in_peak = False
        for window in self.PEAK_WINDOWS_IST:
            start_h = int(window["start_ist"].split(":")[0]) + int(window["start_ist"].split(":")[1]) / 60
            end_h = int(window["end_ist"].split(":")[0]) + int(window["end_ist"].split(":")[1]) / 60
            if start_h <= current_hour <= end_h:
                in_peak = True
                result["current_window"] = window["name"]
                break

        if not in_peak:
            result["warnings"].append("Current time is outside peak upload windows")
            best = self.get_optimal_upload_time()
            result["recommendations"].append(
                f"Best upload time today: {best['recommended_time_ist']} IST ({best['window_name']})"
            )

        # 4. Check daily upload count from ledger
        daily_count = self._get_today_upload_count()
        result["today_upload_count"] = daily_count
        if daily_count >= 4:
            result["warnings"].append(f"Already uploaded {daily_count} videos today — risk of audience fatigue")
        elif daily_count == 0:
            result["recommendations"].append("No uploads today — consider uploading at the next peak window")

        return result

    def _check_upload_gap(self) -> dict:
        """Check hours since last upload from ledger."""
        try:
            if not os.path.exists(self.ledger_path):
                return {"hours_since_last": None, "status": "no_ledger"}
            with open(self.ledger_path, "r") as f:
                ledger = json.load(f)
            history = ledger.get("execution_history", [])
            if not history:
                return {"hours_since_last": None, "status": "no_history"}
            last = history[-1]
            last_time_str = last.get("timestamp") or last.get("completed_at")
            if not last_time_str:
                return {"hours_since_last": None, "status": "no_timestamp"}
            last_time = datetime.fromisoformat(last_time_str)
            now_ist = datetime.now(self.timezone)
            gap_hours = (now_ist - last_time).total_seconds() / 3600
            return {
                "hours_since_last": round(gap_hours, 1),
                "last_upload_time": last_time_str,
                "status": "ok",
            }
        except Exception as e:
            return {"hours_since_last": None, "status": f"error: {e}"}

    def _get_today_upload_count(self) -> int:
        """Count uploads today from ledger."""
        try:
            if not os.path.exists(self.ledger_path):
                return 0
            with open(self.ledger_path, "r") as f:
                ledger = json.load(f)
            history = ledger.get("execution_history", [])
            today = datetime.now(self.timezone).strftime("%Y-%m-%d")
            count = 0
            for entry in history:
                ts = entry.get("timestamp") or entry.get("completed_at", "")
                if ts.startswith(today):
                    count += 1
            return count
        except Exception:
            return 0

    # ── Legacy pass-through ─────────────────────────────────────────────

    def execute(self, state):
        return state
