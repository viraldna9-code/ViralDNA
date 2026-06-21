"""
Upload Reliability v3.0 — VDNA 3.0 Port
API quota monitoring, failover accounts, rate limit backoff, upload queue.
Ported from old pipeline's ReliabilityAgent.
"""
import os, json
from datetime import datetime


class UploadReliability:
    """
    Monitors API quota, manages failover accounts, tracks rate limits,
    and manages the upload queue.
    """

    # YouTube API quota costs (units per operation)
    QUOTA_COSTS = {
        "search.list": 100,
        "videos.list": 1,
        "videos.insert": 1600,
        "videos.update": 50,
        "thumbnails.set": 50,
        "commentThreads.insert": 50,
        "channels.list": 1,
    }
    DAILY_QUOTA_LIMIT = 10000

    def __init__(self, *args, **kwargs):
        self.quota_log_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "api_quota_log.json"
        )
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if os.path.exists(self.quota_log_path):
            try:
                with open(self.quota_log_path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "daily_usage": 0,
            "last_reset": datetime.now().strftime("%Y-%m-%d"),
            "backoff_until": {},
            "failover_active": False,
            "upload_queue": [],
        }

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.quota_log_path), exist_ok=True)
            with open(self.quota_log_path, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception:
            pass

    def _reset_if_new_day(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if self.state.get("last_reset") != today:
            self.state["daily_usage"] = 0
            self.state["last_reset"] = today
            self._save_state()

    def record_api_call(self, operation: str, cost: int = None):
        """Record an API call against the quota."""
        self._reset_if_new_day()
        if cost is None:
            cost = self.QUOTA_COSTS.get(operation, 1)
        self.state["daily_usage"] = self.state.get("daily_usage", 0) + cost
        self._save_state()

    def get_quota_status(self) -> dict:
        """Get current quota status: ok, warning, or critical."""
        self._reset_if_new_day()
        usage = self.state.get("daily_usage", 0)
        pct = (usage / self.DAILY_QUOTA_LIMIT) * 100
        if pct >= 90:
            status = "critical"
        elif pct >= 70:
            status = "warning"
        else:
            status = "ok"
        return {
            "status": status,
            "used": usage,
            "limit": self.DAILY_QUOTA_LIMIT,
            "remaining": self.DAILY_QUOTA_LIMIT - usage,
            "percent_used": round(pct, 1),
            "checked_at": datetime.now().isoformat(),
        }

    def get_active_account(self) -> str:
        """Return active account: 'primary' or 'failover'."""
        if self.state.get("failover_active"):
            return "failover"
        quota = self.get_quota_status()
        if quota["status"] == "critical":
            self.state["failover_active"] = True
            self._save_state()
            return "failover"
        return "primary"

    def get_backoff_seconds(self, service: str = "youtube") -> int:
        """Get remaining backoff seconds for a service (rate limit cooldown)."""
        backoff_until = self.state.get("backoff_until", {}).get(service)
        if backoff_until:
            try:
                from datetime import datetime as dt
                backoff_time = dt.fromisoformat(backoff_until)
                remaining = (backoff_time - dt.now()).total_seconds()
                return max(0, int(remaining))
            except Exception:
                pass
        return 0

    def set_backoff(self, service: str, seconds: int):
        """Set a rate limit backoff for a service."""
        from datetime import datetime as dt, timedelta
        self.state.setdefault("backoff_until", {})
        self.state["backoff_until"][service] = (dt.now() + timedelta(seconds=seconds)).isoformat()
        self._save_state()

    def get_queue_status(self) -> dict:
        """Get upload queue status."""
        queue = self.state.get("upload_queue", [])
        return {
            "queued": len(queue),
            "pending": [q for q in queue if q.get("status") == "pending"],
            "failed": [q for q in queue if q.get("status") == "failed"],
        }

    def enqueue_upload(self, video_path: str, metadata: dict):
        """Add a video to the upload queue."""
        self.state.setdefault("upload_queue", [])
        self.state["upload_queue"].append({
            "video_path": video_path,
            "metadata": metadata,
            "status": "pending",
            "enqueued_at": datetime.now().isoformat(),
        })
        self._save_state()

    def execute(self, state):
        return state
