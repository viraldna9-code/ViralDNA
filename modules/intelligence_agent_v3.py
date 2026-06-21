"""
Intelligence Agent v3.0 — VDNA 3.0 Port
Growth ledger analysis, pattern detection, pipeline recommendations.
Uses existing GrowthObserver from growth_observer.py.
Ported from old pipeline's IntelligenceAgent.
"""
import os, sys

_MODULES_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)

from growth_observer import GrowthObserver
from datetime import datetime


class IntelligenceAgentV3:
    """
    Post-pipeline intelligence: analyzes the full growth ledger to identify
    patterns, recommend improvements, and adjust pipeline parameters.
    """

    def __init__(self, *args, **kwargs):
        self.observer = GrowthObserver()
        self.adjustments = {}

    def analyze(self, state: dict = None) -> dict:
        """Run growth intelligence analysis. Returns recommendations."""
        try:
            ledger = self.observer.load_ledger()
            history = ledger.get("execution_history", [])
            recommendations = []

            if len(history) >= 3:
                # Topic diversity analysis
                recent_topics = [e.get("topic", "") for e in history[-5:]]
                unique_topics = len(set(recent_topics))
                if unique_topics < len(recent_topics) * 0.6:
                    recommendations.append("HIGH: Topic diversity low — expand discovery sources")

                # Upload success rate
                uploads = [e for e in history if e.get("upload_status") == "success"]
                if history:
                    upload_rate = len(uploads) / len(history)
                    if upload_rate < 0.5:
                        recommendations.append(f"MEDIUM: Upload success rate {upload_rate:.0%} — check OAuth scopes")

                # Failure analysis
                total_failures = sum(1 for e in history if e.get("upload_status") == "FAILED")
                failure_rate = total_failures / len(history) if history else 0
                if failure_rate > 0.3:
                    recommendations.append(f"HIGH: High failure rate {failure_rate:.0%} — review pipeline")

            # Always-add growth tips
            recommendations.append("TIP: Upload between 4PM-8PM IST for maximum Telugu audience engagement")
            recommendations.append("TIP: Cover trending topics — cricket, movies, politics, weather")

            # Save to ledger
            try:
                ledger["growth_recommendations"] = [
                    {
                        "priority": r.split(":")[0] if ":" in r else "TIP",
                        "suggestion": r.split(":", 1)[1].strip() if ":" in r else r,
                        "status": "active",
                    }
                    for r in recommendations
                ]
                self.observer.save_ledger(ledger)
            except Exception:
                pass

            return {
                "recommendations": recommendations,
                "history_runs": len(history),
                "analyzed_at": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "recommendations": ["TIP: Upload between 4PM-8PM IST for maximum engagement"],
                "history_runs": 0,
                "error": str(e)[:100],
                "analyzed_at": datetime.now().isoformat(),
            }

    def execute(self, state):
        return state
