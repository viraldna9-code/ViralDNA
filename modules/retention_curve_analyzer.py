"""
Retention Curve Analysis Module — VDNA 3.0
Analyzes YouTube Analytics retention data to identify drop-off points,
optimal video length, and content pacing insights.
"""
import os, json
from datetime import datetime


class RetentionCurveAnalyzer:
    """Analyze YouTube Analytics retention curves for content optimization."""

    def __init__(self, *args, **kwargs):
        self.ledger_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "growth_ledger.json"
        )

    def analyze_retention_curve(self, retention_data: list, video_duration_sec: int = 300) -> dict:
        """
        Analyze a retention curve to find drop-off points and insights.

        Args:
            retention_data: List of {timestamp_sec, retention_pct} dicts
            video_duration_sec: Total video duration in seconds
        """
        if not retention_data:
            return {"error": "No retention data provided", "status": "failed"}

        # Find major drop-off points (>10% drop in 30 seconds)
        drop_offs = []
        for i in range(1, len(retention_data)):
            prev = retention_data[i - 1]
            curr = retention_data[i]
            drop = prev["retention_pct"] - curr["retention_pct"]
            time_delta = curr["timestamp_sec"] - prev["timestamp_sec"]
            if time_delta > 0 and drop / time_delta > 0.33:  # >10% per 30s
                drop_offs.append({
                    "timestamp_sec": curr["timestamp_sec"],
                    "retention_pct": curr["retention_pct"],
                    "drop_magnitude": drop,
                    "timestamp_formatted": f"{curr['timestamp_sec'] // 60}:{curr['timestamp_sec'] % 60:02d}",
                })

        # Calculate average retention
        avg_retention = sum(d["retention_pct"] for d in retention_data) / len(retention_data)

        # Find the "sweet spot" (highest retention period)
        max_retention = max(retention_data, key=lambda x: x["retention_pct"])

        # Calculate first 30-second retention (critical for YouTube algorithm)
        first_30s = [d for d in retention_data if d["timestamp_sec"] <= 30]
        first_30s_avg = sum(d["retention_pct"] for d in first_30s) / len(first_30s) if first_30s else 0

        # Generate insights
        insights = []
        if first_30s_avg < 60:
            insights.append("First 30s retention is low (<60%). Hook needs to be stronger — put the most compelling moment in the first 5 seconds.")
        elif first_30s_avg > 80:
            insights.append("Strong first 30s retention (>80%). Hook is working well.")

        if drop_offs:
            first_drop = drop_offs[0]
            insights.append(f"Major drop-off at {first_drop['timestamp_formatted']} ({first_drop['drop_magnitude']:.1f}% drop). Consider cutting content before this point.")

        if avg_retention < 40:
            insights.append("Overall retention is low (<40%). Video may be too long or pacing is slow.")
        elif avg_retention > 60:
            insights.append("Strong overall retention (>60%). Content pacing is good.")

        # Optimal video length recommendation
        # Find where retention drops below 30%
        below_30 = [d for d in retention_data if d["retention_pct"] < 30]
        if below_30:
            optimal_length = below_30[0]["timestamp_sec"]
            insights.append(f"Recommended max video length: {optimal_length // 60}:{optimal_length % 60:02d} (where retention drops below 30%)")
        else:
            optimal_length = video_duration_sec
            insights.append("Retention stays above 30% throughout — video length is appropriate.")

        return {
            "video_duration_sec": video_duration_sec,
            "average_retention_pct": round(avg_retention, 1),
            "first_30s_retention_pct": round(first_30s_avg, 1),
            "peak_retention": {
                "pct": max_retention["retention_pct"],
                "timestamp_sec": max_retention["timestamp_sec"],
            },
            "drop_off_points": drop_offs[:5],  # Top 5 drop-offs
            "optimal_length_sec": optimal_length,
            "insights": insights,
            "analyzed_at": datetime.now().isoformat(),
        }

    def compare_retention(self, video_a_data: list, video_b_data: list, label_a: str = "A", label_b: str = "B") -> dict:
        """Compare retention curves between two videos."""
        analysis_a = self.analyze_retention_curve(video_a_data)
        analysis_b = self.analyze_retention_curve(video_b_data)

        winner = label_a if analysis_a["average_retention_pct"] > analysis_b["average_retention_pct"] else label_b

        return {
            "comparison": f"{label_a} vs {label_b}",
            "winner": winner,
            f"{label_a}_avg_retention": analysis_a["average_retention_pct"],
            f"{label_b}_avg_retention": analysis_b["average_retention_pct"],
            f"{label_a}_first_30s": analysis_a["first_30s_retention_pct"],
            f"{label_b}_first_30s": analysis_b["first_30s_retention_pct"],
            "recommendation": f"{winner} has better retention. Analyze what {winner} does differently in the first 30 seconds.",
            "compared_at": datetime.now().isoformat(),
        }

    def execute(self, state):
        return state
