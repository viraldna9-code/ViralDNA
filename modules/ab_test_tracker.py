"""
A/B Test Tracker v2.0
Persistent A/B test management with ledger-based result tracking.
Tracks title variants, thumbnail tests, and description experiments.
"""
import os, json
from datetime import datetime


class ABTestTracker:
    """
    Full A/B test lifecycle management.
    Persists tests to disk, tracks results, declares winners.
    """

    TEST_STATUSES = ["created", "running", "completed", "archived"]

    # High-emotion hook words that tend to increase CTR
    POSITIVE_HOOKS = ["breaking", "exclusive", "revealed", "shocking", "urgent"]
    NEGATIVE_HOOKS = ["warning", "alert", "danger"]

    def __init__(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "ab_test_db.json"
        )
        self._load_db()

    # ── Test Lifecycle ──────────────────────────────────────────────────

    def create_test(self, test_type: str, test_name: str,
                    control: dict, variant: dict,
                    topic: str = "", video_id: str = "") -> dict:
        """
        Create a new A/B test.
        Called by CTROptimizationAgent with:
          create_test("title", "CTR title test variant 0",
                      {"title": best_title}, {"title": variant_title},
                      topic=..., video_id=...)
        """
        test = {
            "id": f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.db['tests'])}",
            "test_type": test_type,
            "test_name": test_name,
            "control": control,
            "variant": variant,
            "topic": topic,
            "video_id": video_id or f"vid_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "status": "running",
            "created_at": datetime.now().isoformat(),
            "results": {"control_views": 0, "variant_views": 0,
                        "control_ctr": 0.0, "variant_ctr": 0.0},
            "winner": None,
        }
        self.db["tests"].append(test)
        self._save_db()
        return {"status": "created", "test_id": test["id"], "test_name": test_name}

    def get_active_tests(self) -> list:
        """Return list of currently running tests."""
        return [t for t in self.db.get("tests", []) if t.get("status") == "running"]

    def record_result(self, test_id: str, variant: str, views: int, ctr: float):
        """Record test result data (called when analytics data available)."""
        for test in self.db.get("tests", []):
            if test["id"] == test_id:
                if variant == "control":
                    test["results"]["control_views"] = views
                    test["results"]["control_ctr"] = ctr
                elif variant == "variant":
                    test["results"]["variant_views"] = views
                    test["results"]["variant_ctr"] = ctr

                # Auto-declare winner if sufficient data
                if test["results"]["control_views"] >= 1000 and test["results"]["variant_views"] >= 1000:
                    if test["results"]["variant_ctr"] > test["results"]["control_ctr"]:
                        test["winner"] = "variant"
                    else:
                        test["winner"] = "control"
                    test["status"] = "completed"
                    test["completed_at"] = datetime.now().isoformat()

                self._save_db()
                return True
        return False

    def get_winners(self) -> list:
        """Return completed tests with declared winners."""
        return [t for t in self.db.get("tests", [])
                if t.get("status") == "completed" and t.get("winner")]

    def get_stats(self) -> dict:
        """Return overall test statistics."""
        tests = self.db.get("tests", [])
        active = [t for t in tests if t.get("status") == "running"]
        completed = [t for t in tests if t.get("status") == "completed"]
        winners = [t for t in completed if t.get("winner")]
        return {
            "total_tests": len(tests),
            "active_tests": len(active),
            "completed_tests": len(completed),
            "winners_declared": len(winners),
            "variant_wins": sum(1 for t in winners if t.get("winner") == "variant"),
            "control_wins": sum(1 for t in winners if t.get("winner") == "control"),
        }

    def archive_old_tests(self, max_age_days: int = 30):
        """Archive tests older than max_age_days."""
        now = datetime.now()
        for test in self.db.get("tests", []):
            if test.get("status") == "running":
                created = datetime.fromisoformat(test["created_at"]) if test.get("created_at") else now
                age_days = (now - created).days
                if age_days > max_age_days:
                    test["status"] = "archived"
        self._save_db()

    # ── Legacy compatibility ────────────────────────────────────────────

    def get_test_history(self) -> list:
        """Return all tests (for learning)."""
        return self.db.get("tests", [])

    # ── Internal ────────────────────────────────────────────────────────

    def _load_db(self):
        try:
            if os.path.exists(self.db_path):
                with open(self.db_path, "r") as f:
                    self.db = json.load(f)
            else:
                self.db = {"tests": [], "stats": {"total_created": 0, "total_completed": 0}}
        except Exception:
            self.db = {"tests": [], "stats": {"total_created": 0, "total_completed": 0}}

    def _save_db(self):
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with open(self.db_path, "w") as f:
                json.dump(self.db, f, indent=2, default=str)
        except Exception:
            pass

    def execute(self, state):
        return state
