"""
Retention Analyzer v2.0
CTR benchmarking, series funnel planning, next-video comment suggestions.
Returns structured dicts matching RetentionOptimizationAgent expectations.
"""
import os, json
from datetime import datetime


class RetentionAnalyzer:
    def __init__(self, *args, **kwargs):
        self.ledger_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "growth_ledger.json"
        )
        # Industry benchmark CTR% by category (heuristic defaults)
        self.category_benchmarks = {
            "news_politics": {"avg_ctr": 0.05, "good_ctr": 0.07, "excellent_ctr": 0.10},
            "entertainment": {"avg_ctr": 0.06, "good_ctr": 0.09, "excellent_ctr": 0.12},
            "technology": {"avg_ctr": 0.05, "good_ctr": 0.08, "excellent_ctr": 0.11},
            "sports": {"avg_ctr": 0.06, "good_ctr": 0.08, "excellent_ctr": 0.10},
            "health": {"avg_ctr": 0.05, "good_ctr": 0.07, "excellent_ctr": 0.09},
            "economics": {"avg_ctr": 0.04, "good_ctr": 0.06, "excellent_ctr": 0.08},
            "crime": {"avg_ctr": 0.06, "good_ctr": 0.09, "excellent_ctr": 0.12},
            "disaster": {"avg_ctr": 0.07, "good_ctr": 0.10, "excellent_ctr": 0.14},
        }

    # ── CTR Benchmarking ────────────────────────────────────────────────

    def benchmark_ctr(self, video_id: str, category: str, actual_ctr: float) -> dict:
        """
        Compare a video's CTR against category benchmarks.
        Returns {"video_id", "category", "actual_ctr", "benchmark", "rating", "recommendation"}.
        """
        bench = self.category_benchmarks.get(category, self.category_benchmarks["news_politics"])

        if actual_ctr >= bench["excellent_ctr"]:
            rating = "excellent"
            recommendation = "Thumbnail and title are top-perfect. Replicate this style."
        elif actual_ctr >= bench["good_ctr"]:
            rating = "good"
            recommendation = "Above average. Test one variable (title or thumbnail) for improvement."
        elif actual_ctr >= bench["avg_ctr"]:
            rating = "average"
            recommendation = "Below potential. Try stronger hook words in title and more contrast in thumbnail."
        else:
            rating = "below_average"
            recommendation = "Needs significant improvement. Consider A/B testing new title + thumbnail combination."

        result = {
            "video_id": video_id,
            "category": category,
            "actual_ctr": actual_ctr,
            "benchmark_avg": bench["avg_ctr"],
            "benchmark_good": bench["good_ctr"],
            "benchmark_excellent": bench["excellent_ctr"],
            "rating": rating,
            "recommendation": recommendation,
            "benchmarked_at": datetime.now().isoformat(),
        }

        # Store in ledger
        self._store_retention_analysis(result)
        return result

    # ── Series Funnel Planning ──────────────────────────────────────────

    def plan_series_funnel(self, topic_title: str, num_parts: int = 3) -> dict:
        """
        Plan a multi-part series funnel for a topic.
        Returns series structure with part titles, hooks, and CTAs.
        """
        clean_title = topic_title.strip()

        parts = []
        for i in range(1, num_parts + 1):
            if i == 1:
                hook = f"Part 1: What happened and why it matters"
                cta = f"Part 2 drops tomorrow — subscribe and hit the bell so you don't miss it."
            elif i < num_parts:
                hook = f"Part {i}: Deep dive — what they're not telling you"
                cta = f"Part {i + 1} is coming. Make sure you're subscribed."
            else:
                hook = f"Part {i}: Final analysis — what happens next"
                cta = f"That's the full story. If this helped you understand, subscribe for more Telugu news breakdowns."

            parts.append({
                "part_number": i,
                "title": f"{clean_title} — Part {i}",
                "hook": hook,
                "end_cta": cta,
                "target_duration_sec": 480 if i == 1 else 360,  # Part 1 longer
                "thumbnail_variant": i,
            })

        return {
            "series_title": clean_title,
            "total_parts": num_parts,
            "parts": parts,
            "funnel_strategy": "Part 1 hooks → Part 2 deepens → Part 3 concludes with subscribe CTA",
            "planned_at": datetime.now().isoformat(),
        }

    # ── Next Video Comment Suggestion ───────────────────────────────────

    def build_next_video_comment(self) -> str:
        """
        Generate a suggested pinned comment for the next video
        to drive engagement and session time.
        """
        templates = [
            "What do you think about this? Drop your thoughts below 👇",
            "Is this happening in your area? Let us know in the comments.",
            "Share this with someone who needs to see this. Tag them below.",
            "What should we cover next? Tell us in the comments — we read every one.",
            "If you're watching from the US, UK, or Canada — where are you from? Comment below!",
            "Agree or disagree? Let's discuss. Drop your opinion below 👇",
        ]
        # Rotate based on day of week for variety
        day_index = datetime.now().weekday() % len(templates)
        return templates[day_index]

    # ── Internal ────────────────────────────────────────────────────────

    def _store_retention_analysis(self, result: dict):
        """Store retention analysis result in the growth ledger."""
        try:
            ledger = {}
            if os.path.exists(self.ledger_path):
                with open(self.ledger_path, "r") as f:
                    ledger = json.load(f)

            if "retention_analysis" not in ledger:
                ledger["retention_analysis"] = []
            ledger["retention_analysis"].append(result)
            ledger["retention_analysis"] = ledger["retention_analysis"][-50:]

            os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
            with open(self.ledger_path, "w") as f:
                json.dump(ledger, f, indent=2, default=str)
        except Exception:
            pass  # Non-fatal

    # ── Legacy pass-through ─────────────────────────────────────────────

    def execute(self, state):
        return state
