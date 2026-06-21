"""
Continuous Auditor v3.0 — VDNA 3.0 Port
Pipeline health auditing, telemetry commit, performance logging.
Ported from old pipeline's ContinuousAuditorAgent.
"""
import os, json
from datetime import datetime


class ContinuousAuditor:
    """
    Post-pipeline continuous auditor: records execution traces,
    checks pipeline health, and commits telemetry to the growth ledger.
    """

    def __init__(self, *args, **kwargs):
        self.ledger_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "growth_ledger.json"
        )

    def audit_pipeline_run(self, state: dict) -> dict:
        """Audit a completed pipeline run and return health report."""
        errors = state.get("errors", [])
        compiled = state.get("compiled_videos", [])
        upload = state.get("upload_results", {})

        # Count successful uploads
        upload_count = 0
        if isinstance(upload, list):
            upload_count = sum(1 for r in upload if isinstance(r, dict) and r.get("status") == "success")
        elif isinstance(upload, dict):
            upload_count = 1 if upload.get("status") == "success" else 0

        total_videos = len(compiled) if isinstance(compiled, list) else 0
        error_count = len(errors) if isinstance(errors, list) else 0

        # Health score
        health = 100
        if error_count > 0:
            health -= error_count * 10
        if total_videos > 0 and upload_count < total_videos:
            health -= (total_videos - upload_count) * 15
        health = max(0, health)

        if health >= 80:
            status = "healthy"
        elif health >= 50:
            status = "degraded"
        else:
            status = "critical"

        return {
            "status": status,
            "health_score": health,
            "videos_produced": total_videos,
            "videos_uploaded": upload_count,
            "errors": error_count,
            "audited_at": datetime.now().isoformat(),
        }

    def commit_telemetry(self, state: dict) -> bool:
        """Commit pipeline execution telemetry to the growth ledger."""
        try:
            ledger = {}
            if os.path.exists(self.ledger_path):
                with open(self.ledger_path) as f:
                    ledger = json.load(f)

            history = ledger.setdefault("execution_history", [])
            topic = state.get("selected_topic", {})
            upload = state.get("upload_results", {})

            entry = {
                "timestamp": datetime.now().isoformat(),
                "topic": topic.get("title", "unknown") if isinstance(topic, dict) else str(topic),
                "category": topic.get("category", "unknown") if isinstance(topic, dict) else "unknown",
                "videos_produced": len(state.get("compiled_videos", [])),
                "upload_status": upload.get("overall_status", "unknown") if isinstance(upload, dict) else "unknown",
                "error_count": len(state.get("errors", [])),
            }
            history.append(entry)

            # Keep last 200 entries
            if len(history) > 200:
                history = history[-200:]
            ledger["execution_history"] = history

            os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
            with open(self.ledger_path, "w") as f:
                json.dump(ledger, f, indent=2)
            return True
        except Exception:
            return False

    def execute(self, state):
        return state
