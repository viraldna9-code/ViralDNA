"""
Upload Reliability Manager v2.0
API quota monitoring, rate limit backoff, upload queue management, account health.
Prevents silent pipeline failures from quota exhaustion or rate limiting.
"""
import os, json, time
from datetime import datetime, timedelta


class UploadReliabilityManager:
    """
    Manages pipeline reliability: quota tracking, rate limiting,
    upload queue, and account failover state.
    """

    # YouTube Data API v3 default quota: 10,000 units/day
    # Cost reference: channels.list=1, videos.insert=1600, thumbnails.set=50,
    #                 search.list=100, videos.list=1
    DEFAULT_DAILY_QUOTA = 10000
    QUOTA_COSTS = {
        "videos.insert": 1600,
        "thumbnails.set": 50,
        "channels.list": 1,
        "videos.list": 1,
        "search.list": 100,
        "commentThreads.insert": 50,
        "comments.insert": 50,
        "subscriptions.list": 1,
    }

    def __init__(self, *args, **kwargs):
        self.ledger_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "growth_ledger.json"
        )
        self.state_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "reliability_state.json"
        )
        # In-memory rate limit tracking (persisted to reliability_state.json)
        self._rate_limits = {}  # {service: epoch_seconds_when_clear}
        self._load_state()

    # ── Quota Status ────────────────────────────────────────────────────

    def get_quota_status(self) -> dict:
        """
        Returns current API quota usage estimate and status.
        Reads from the growth ledger's daily usage tracking.
        """
        used = 0
        today = datetime.now().strftime("%Y-%m-%d")

        try:
            if os.path.exists(self.ledger_path):
                with open(self.ledger_path, "r") as f:
                    ledger = json.load(f)
                usage_log = ledger.get("api_quota_usage", {})
                used = usage_log.get(today, 0)
        except Exception:
            used = 0

        remaining = max(0, self.DEFAULT_DAILY_QUOTA - used)
        pct_used = (used / self.DEFAULT_DAILY_QUOTA) * 100 if self.DEFAULT_DAILY_QUOTA > 0 else 0

        if pct_used >= 90:
            status = "critical"
        elif pct_used >= 75:
            status = "warning"
        elif pct_used >= 50:
            status = "moderate"
        else:
            status = "healthy"

        # Estimate how many uploads remain
        uploads_remaining = remaining // self.QUOTA_COSTS["videos.insert"] if self.QUOTA_COSTS["videos.insert"] > 0 else 0

        return {
            "status": status,
            "daily_limit": self.DEFAULT_DAILY_QUOTA,
            "used_today": used,
            "remaining": remaining,
            "pct_used": round(pct_used, 1),
            "estimated_uploads_remaining": uploads_remaining,
            "reset_time_utc": "00:00 (Pacific Time — YouTube quota resets at midnight PT)",
            "recommendation": self._quota_recommendation(status, uploads_remaining),
        }

    # ── Account Health ──────────────────────────────────────────────────

    def get_active_account(self) -> str:
        """
        Returns which account is currently active ('primary' or failover).
        Reads from reliability state file.
        """
        try:
            if os.path.exists(self.state_path):
                with open(self.state_path, "r") as f:
                    state = json.load(f)
                active = state.get("active_account", "primary")
                failover_reason = state.get("failover_reason", "")
                activated_at = state.get("failover_activated_at", "")
                return active
        except Exception:
            pass
        return "primary"

    def switch_to_failover(self, reason: str = "quota_exhausted"):
        """Switch to failover account (for future multi-account support)."""
        try:
            state = {}
            if os.path.exists(self.state_path):
                with open(self.state_path, "r") as f:
                    state = json.load(f)
            state["active_account"] = "failover"
            state["failover_reason"] = reason
            state["failover_activated_at"] = datetime.now().isoformat()
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, "w") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    # ── Rate Limit Backoff ──────────────────────────────────────────────

    def get_backoff_seconds(self, service: str = "youtube") -> int:
        """
        Returns remaining backoff seconds for a service.
        Returns 0 if the service is clear to use.
        """
        until_epoch = self._rate_limits.get(service, 0)
        remaining = max(0, int(until_epoch - time.time()))
        return remaining

    def set_backoff(self, service: str = "youtube", seconds: int = 60):
        """Set a rate limit backoff for a service."""
        self._rate_limits[service] = time.time() + seconds
        self._save_state()

    # ── Upload Queue ────────────────────────────────────────────────────

    def get_queue_status(self) -> dict:
        """
        Returns current upload queue status.
        Reads from reliability state.
        """
        try:
            if os.path.exists(self.state_path):
                with open(self.state_path, "r") as f:
                    state = json.load(f)
                queue = state.get("upload_queue", [])
                return {
                    "queued": len(queue),
                    "pending": [q for q in queue if q.get("status") == "pending"],
                    "failed_last_24h": state.get("failed_uploads_24h", 0),
                    "last_error": state.get("last_error", None),
                    "queue_items": queue[:5],  # Show first 5 for debugging
                }
        except Exception:
            pass
        return {"queued": 0, "pending": [], "failed_last_24h": 0, "last_error": None, "queue_items": []}

    def enqueue_upload(self, video_path: str, metadata: dict):
        """Add an item to the upload queue."""
        try:
            state = {}
            if os.path.exists(self.state_path):
                with open(self.state_path, "r") as f:
                    state = json.load(f)
            if "upload_queue" not in state:
                state["upload_queue"] = []
            state["upload_queue"].append({
                "video_path": video_path,
                "title": metadata.get("title", ""),
                "status": "pending",
                "queued_at": datetime.now().isoformat(),
            })
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, "w") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    # ── Quota Tracking (called by youtube_uploader after each API call) ──

    def record_api_usage(self, endpoint: str, units: int = 1):
        """Record API quota usage in the growth ledger."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            ledger = {}
            if os.path.exists(self.ledger_path):
                with open(self.ledger_path, "r") as f:
                    ledger = json.load(f)
            if "api_quota_usage" not in ledger:
                ledger["api_quota_usage"] = {}
            ledger["api_quota_usage"][today] = ledger["api_quota_usage"].get(today, 0) + units
            os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
            with open(self.ledger_path, "w") as f:
                json.dump(ledger, f, indent=2, default=str)
        except Exception:
            pass

    # ── Internal ────────────────────────────────────────────────────────

    def _load_state(self):
        try:
            if os.path.exists(self.state_path):
                with open(self.state_path, "r") as f:
                    state = json.load(f)
                self._rate_limits = state.get("rate_limits", {})
        except Exception:
            self._rate_limits = {}

    def _save_state(self):
        try:
            state = {}
            if os.path.exists(self.state_path):
                with open(self.state_path, "r") as f:
                    state = json.load(f)
            state["rate_limits"] = self._rate_limits
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, "w") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def _quota_recommendation(self, status: str, uploads_remaining: int) -> str:
        if status == "critical":
            return f"CRITICAL: Only ~{uploads_remaining} uploads remaining today. Stop non-essential API calls."
        elif status == "warning":
            return f"WARNING: ~{uploads_remaining} uploads remaining. Prioritize main + 1 short."
        elif status == "moderate":
            return f"Moderate usage. ~{uploads_remaining} uploads remaining. Full pipeline OK."
        return f"Healthy quota. ~{uploads_remaining} uploads remaining. Pipeline running normally."

    # ── Legacy pass-through ─────────────────────────────────────────────

    def execute(self, state):
        return state
